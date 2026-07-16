"""Poll until a payment reaches a terminal state."""

from __future__ import annotations

import random
import time
from typing import Any, Literal

from .config import POLL_JITTER_MS
from .poll_interval import is_terminal_transaction_status, resolve_poll_interval_ms
from .slang import Err, Ok, Result
from .transport import parse_error
from .types import GetStatusInput, GetTransactionInput, StatusResponse, Transaction

OnDelayedBehavior = Literal["wait", "return"]

TIMEOUT_MESSAGE = "Timed out waiting for the transaction status to update"


def poll_until_terminal(deps: dict[str, Any]) -> Result[Transaction, str]:
    """Block until terminal, merchant caps, or on_delayed return."""
    poll_start = time.time() * 1000
    attempts = 0
    reference: str = deps["reference"]
    fetch_status = deps["fetch_status"]
    fetch_transaction = deps["fetch_transaction"]
    poll_interval_ms: int = deps["poll_interval_ms"]
    max_poll_duration_ms: int | None = deps.get("max_poll_duration_ms")
    max_poll_attempts: int | None = deps.get("max_poll_attempts")
    on_delayed: OnDelayedBehavior = deps.get("on_delayed", "wait")

    while True:
        if max_poll_attempts is not None and attempts >= max_poll_attempts:
            return Err(TIMEOUT_MESSAGE)
        if (
            max_poll_duration_ms is not None
            and time.time() * 1000 - poll_start >= max_poll_duration_ms
        ):
            return Err(TIMEOUT_MESSAGE)

        attempts += 1
        status_result = fetch_status(GetStatusInput(reference=reference))
        if status_result.is_err:
            parsed = parse_error(status_result.error)
            if parsed.category == "not_found":
                time.sleep(poll_interval_ms / 1000)
                continue
            return Err(parsed.message)

        status: StatusResponse = status_result.value
        if is_terminal_transaction_status(status.status):
            tx_result = fetch_transaction(GetTransactionInput(reference=reference))
            if tx_result.is_ok:
                return Ok(tx_result.value)
            return Err(tx_result.error)

        if status.delayed and on_delayed == "return":
            tx_result = fetch_transaction(GetTransactionInput(reference=reference))
            if tx_result.is_ok:
                return Ok(tx_result.value)
            return Err(tx_result.error)

        interval = resolve_poll_interval_ms(
            base_interval_ms=poll_interval_ms,
            poll_start_time_ms=poll_start,
        )
        time.sleep((interval + random.random() * POLL_JITTER_MS) / 1000)
