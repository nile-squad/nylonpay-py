"""Reachability tracker: remember the last successful round-trip.

A recent success (5 minutes) means Nylon answered, so the next signed
operations go out with no extra check. After an unreachable failure, the
next SDK operation is checked before it is attempted; polls inside the
re-check pause are skipped without another request.
"""

from __future__ import annotations

import errno
import socket
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .config import (
    REACHABILITY_DOWN_RECHECK_MS,
    REACHABILITY_SUCCESS_FRESH_MS,
    UNREACHABLE_CODE,
    UNREACHABLE_HOST_OFFLINE,
    UNREACHABLE_NYLON_DOWN,
)
from .slang import Err, Result
from .types import SdkError, UnreachableReason

GATEWAY_DOWN_STATUSES = frozenset({502, 503, 504})

_HOST_OFFLINE_ERRNOS = frozenset(
    {
        errno.ENETUNREACH,
        errno.ENETDOWN,
        errno.EHOSTUNREACH,
        getattr(errno, "ENONET", -1),
    }
)

_HOST_OFFLINE_TEXT = (
    "enotfound",
    "eai_again",
    "eai_noname",
    "enetunreach",
    "enetdown",
    "ehostunreach",
    "enonet",
    "getaddrinfo",
    "could not resolve host",
    "couldn't resolve host",
    "failed to resolve",
    "name or service not known",
    "nodename nor servname",
    "err_name_not_resolved",
    "no such host",
    "temporary failure in name resolution",
)


def _walk_exceptions(error: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    out: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        out.append(current)
        current = current.__cause__ or current.__context__
    return out


def _error_text(error: BaseException) -> str:
    parts = [str(error), type(error).__name__]
    for item in _walk_exceptions(error):
        parts.append(str(item))
        parts.append(type(item).__name__)
    return " ".join(parts).lower()


def classify_unreachable(error: BaseException) -> UnreachableReason:
    """Map a thrown transport error to one of the two merchant-facing reasons."""
    for item in _walk_exceptions(error):
        if isinstance(item, socket.gaierror):
            return UNREACHABLE_HOST_OFFLINE
        if isinstance(item, OSError) and item.errno in _HOST_OFFLINE_ERRNOS:
            return UNREACHABLE_HOST_OFFLINE

    text = _error_text(error)
    if any(token in text for token in _HOST_OFFLINE_TEXT):
        return UNREACHABLE_HOST_OFFLINE
    return UNREACHABLE_NYLON_DOWN


def classify_http_status(status_code: int) -> UnreachableReason | None:
    """502/503/504 mean Nylon's edge said the service is down."""
    if status_code in GATEWAY_DOWN_STATUSES:
        return UNREACHABLE_NYLON_DOWN
    return None


def unreachable_sdk_error(reason: UnreachableReason) -> SdkError:
    return SdkError(
        category="network",
        message=reason,
        retryable=True,
        code=UNREACHABLE_CODE,
    )


def serialize_unreachable(reason: UnreachableReason) -> str:
    import json

    error = unreachable_sdk_error(reason)
    payload: dict[str, Any] = {
        "category": error.category,
        "message": error.message,
        "retryable": error.retryable,
        "code": error.code,
    }
    return json.dumps(payload)


def create_reachability_tracker(
    *,
    probe: Callable[[], UnreachableReason | None] | None = None,
    now: Callable[[], float] | None = None,
    success_fresh_ms: int = REACHABILITY_SUCCESS_FRESH_MS,
    down_recheck_ms: int = REACHABILITY_DOWN_RECHECK_MS,
) -> dict[str, Any]:
    """Create a per-transport reachability tracker.

    ``before_send`` returns an Err the caller MUST return instead of
    sending, or ``None`` to proceed. A recent successful round-trip skips
    the check for 5 minutes.
    """
    now_fn = now if now is not None else (lambda: datetime.now(timezone.utc).timestamp() * 1000)
    memory: dict[str, Any] = {
        "last_success_at": None,
        "last_failed": False,
        "last_reason": None,
        "last_check_at": None,
    }

    def _run_check() -> Result[Any, str] | None:
        memory["last_check_at"] = now_fn()
        if probe is None:
            return None
        reason = probe()
        if reason is None:
            note_up()
            return None
        memory["last_failed"] = True
        memory["last_reason"] = reason
        return Err(serialize_unreachable(reason))

    def before_send() -> Result[Any, str] | None:
        t = now_fn()
        last_check = memory["last_check_at"]
        last_success = memory["last_success_at"]

        if last_check is not None and t - last_check >= success_fresh_ms:
            return _run_check()

        if (
            not memory["last_failed"]
            and last_success is not None
            and t - last_success < success_fresh_ms
        ):
            return None

        if memory["last_failed"]:
            if last_check is not None and t - last_check < down_recheck_ms:
                return Err(
                    serialize_unreachable(memory["last_reason"] or UNREACHABLE_NYLON_DOWN)
                )
            return _run_check()

        if last_success is None:
            return None

        return _run_check()

    def note_down(reason: UnreachableReason) -> None:
        memory["last_failed"] = True
        memory["last_reason"] = reason
        memory["last_check_at"] = now_fn()

    def note_up() -> None:
        t = now_fn()
        memory["last_success_at"] = t
        memory["last_check_at"] = t
        memory["last_failed"] = False
        memory["last_reason"] = None

    return {
        "before_send": before_send,
        "note_down": note_down,
        "note_up": note_up,
    }
