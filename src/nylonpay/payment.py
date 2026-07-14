"""Payment instance with event emission for transaction lifecycle.

Creates an event-driven payment instance that polls for status updates,
emits lifecycle events, and supports blocking until terminal state.

Fully synchronous — no asyncio. Events fire as callbacks during ``wait()``,
which runs a polling loop with ``time.sleep`` between polls.

Factory pattern — :func:`create_payment_instance` returns a plain object
(``SimpleNamespace``) with closure-based methods. No classes.
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

from .config import (
    DEFAULT_MAX_POLL_INTERVAL_MS,
    POLL_JITTER_MS,
)
from .poll_interval import resolve_poll_interval_ms
from .pubsub import create_emitter
from .transport import parse_error
from .types import (
    EventData,
    GetStatusInput,
    GetTransactionInput,
    PaymentEvent,
    PaymentEventHandler,
    PaymentInstance,
    SdkError,
    SdkErrorCategory,
    StatusResponse,
    Transaction,
    TransactionStatus,
)

# --- Status → Event mapping ---

STATUS_TO_EVENT: dict[str, PaymentEvent] = {
    "pending": "processing",
    "processing": "processing",
    "successful": "success",
    "failed": "failed",
    "cancelled": "cancelled",
}

TERMINAL_STATES: frozenset[str] = frozenset({"successful", "failed", "cancelled"})


def _status_to_event(status: str) -> PaymentEvent | None:
    """Map a transaction status to its corresponding payment event."""
    return STATUS_TO_EVENT.get(status)


def _normalize_status(raw: str) -> TransactionStatus:
    """Normalise raw backend status strings. ``'completed'`` → ``'successful'``."""
    if raw == "completed":
        return "successful"
    return raw  # ty: ignore[invalid-return-type]


def create_payment_instance(
    initial_response: dict[str, Any],
    deps: dict[str, Any],
) -> PaymentInstance:
    """Create a payment instance with polling and event emission.

    ``initial_response`` carries ``reference`` and ``status`` from the
    initiation call. ``deps`` injects ``fetch_status``, ``fetch_transaction``,
    optional poll config, and an optional ``initial_error`` for backend
    rejections that surface as events rather than exceptions.

    Events fire during ``wait()`` — the polling loop runs inside it and
    calls registered callbacks as the status changes. If ``wait()`` is
    never called, no polling occurs.

    Returns a ``SimpleNamespace`` with ``reference``, ``status``,
    ``on``, ``once``, ``off``, ``wait`` — satisfies ``PaymentInstance``
    protocol without a class.
    """
    emitter = create_emitter()

    state: dict[str, Any] = {
        "reference": initial_response["reference"],
        "status": _normalize_status(initial_response["status"]),
        "transaction": None,
        "last_status_event": None,
        "resolved": False,
        "poll_attempts": 0,
        "poll_start_time": time.time() * 1000,
        "emitter": emitter,
        "fetch_status": deps["fetch_status"],
        "fetch_transaction": deps["fetch_transaction"],
        "poll_interval_ms": deps.get("poll_interval_ms", DEFAULT_MAX_POLL_INTERVAL_MS),
        "max_poll_duration": deps.get("max_poll_duration"),
        "max_poll_attempts": deps.get("max_poll_attempts"),
        "on_delayed": deps.get("on_delayed", "wait"),
        "early_return_pending": False,
        "pending_error": None,
    }

    def set_status(new_status: TransactionStatus) -> None:
        """Update status in both state dict and on the public object."""
        state["status"] = new_status
        payment_instance.status = new_status

    def emit_event(
        event: PaymentEvent,
        error: str | None = None,
        category: SdkErrorCategory | None = None,
        retryable: bool | None = None,
    ) -> None:
        """Emit a lifecycle event with current transaction data."""
        data = EventData(
            event=event,
            reference=state["reference"],
            timestamp=datetime.now(timezone.utc).isoformat(),
            transaction=state["transaction"],
            error=error,
            category=category,
            retryable=retryable,
        )
        emitter["emit"](event, data)

    def handle_terminal_state(status: TransactionStatus) -> None:
        """Fetch full transaction record and emit terminal event."""
        tx_result = state["fetch_transaction"](GetTransactionInput(reference=state["reference"]))
        if tx_result.is_ok:
            state["transaction"] = tx_result.value
            event = _status_to_event(status)
            if event is not None:
                error_msg = None
                if status == "failed" and state["transaction"] is not None:
                    error_msg = state["transaction"].failure_reason
                emit_event(event, error=error_msg)
        else:
            emit_event("error", error="Could not retrieve the transaction details")
        state["resolved"] = True

    def handle_status_update(response: StatusResponse) -> None:
        """Process a status response from polling."""
        if state["resolved"]:
            return

        if response.reference != state["reference"]:
            emit_event(
                "error",
                error="Received a status update for a different transaction",
                category="internal",
            )
            state["resolved"] = True
            return

        new_status = _normalize_status(response.status)
        set_status(new_status)

        if (
            response.delayed
            and state["on_delayed"] == "return"
            and new_status not in TERMINAL_STATES
        ):
            tx_result = state["fetch_transaction"](
                GetTransactionInput(reference=state["reference"])
            )
            if tx_result.is_ok:
                state["transaction"] = tx_result.value
            state["early_return_pending"] = True
            state["resolved"] = True
            return

        # Dedupe by event, not raw status
        event = _status_to_event(new_status)
        if event is None or event == state["last_status_event"]:
            return
        state["last_status_event"] = event

        if new_status in TERMINAL_STATES:
            handle_terminal_state(new_status)
            return

        emit_event(event)

    def poll_once() -> None:
        """Execute one polling cycle."""
        if state["resolved"]:
            return

        max_attempts = state["max_poll_attempts"]
        if max_attempts is not None and state["poll_attempts"] >= max_attempts:
            emit_event(
                "error",
                error="Timed out waiting for the transaction status to update",
                category="timeout",
            )
            state["resolved"] = True
            return

        max_duration = state["max_poll_duration"]
        current_ms = time.time() * 1000
        if max_duration is not None and current_ms - state["poll_start_time"] >= max_duration:
            emit_event(
                "error",
                error="Timed out waiting for the transaction status to update",
                category="timeout",
            )
            state["resolved"] = True
            return

        state["poll_attempts"] += 1

        result = state["fetch_status"](GetStatusInput(reference=state["reference"]))

        if result.is_ok:
            handle_status_update(result.value)
        else:
            parsed = parse_error(result.error)
            if parsed.category == "not_found":
                return
            emit_event("error", parsed.message, parsed.category, parsed.retryable)
            state["resolved"] = True

    def wait_fn() -> Transaction | None:
        """Block until terminal state.

        Emits any pending initial error, then polls at jittered intervals
        until the transaction reaches a terminal state. Event callbacks
        fire as the status changes during this loop.
        """
        # Handle pending initial error (backend rejection at initiation)
        if state["pending_error"] is not None:
            err: SdkError = state["pending_error"]
            state["pending_error"] = None
            emit_event("error", err.message, err.category, err.retryable)
            return None

        if state["resolved"]:
            return state["transaction"] if state["status"] == "successful" else None

        # Emit initial event if status maps to one
        initial_event = _status_to_event(state["status"])
        if initial_event is not None and initial_event != state["last_status_event"]:
            state["last_status_event"] = initial_event
            emit_event(initial_event)

        # If already in terminal state at creation, handle it
        if state["status"] in TERMINAL_STATES:
            handle_terminal_state(state["status"])
        else:
            # Poll until resolved
            while not state["resolved"]:
                poll_once()
                if state["resolved"]:
                    break
                delay = (
                    resolve_poll_interval_ms(
                        base_interval_ms=state["poll_interval_ms"],
                        poll_start_time_ms=state["poll_start_time"],
                    )
                    + random.random() * POLL_JITTER_MS
                ) / 1000
                time.sleep(delay)

        if state.get("early_return_pending") and state["transaction"] is not None:
            return state["transaction"]

        return state["transaction"] if state["status"] == "successful" else None

    # --- Public API closures ---

    def on_fn(event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        emitter["on"](event, handler)
        return payment_instance

    def once_fn(event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        emitter["once"](event, handler)
        return payment_instance

    def off_fn(event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        emitter["off"](event, handler)
        return payment_instance

    # --- Build the public object (no class, just closures on SimpleNamespace) ---

    payment_instance = cast(
        "PaymentInstance",
        SimpleNamespace(
            reference=state["reference"],
            status=state["status"],
            on=on_fn,
            once=once_fn,
            off=off_fn,
            wait=wait_fn,
        ),
    )

    # Store initial error for wait() to emit (handlers aren't registered yet)
    initial_error: SdkError | None = deps.get("initial_error")
    if initial_error is not None:
        state["resolved"] = True
        state["pending_error"] = initial_error

    return payment_instance
