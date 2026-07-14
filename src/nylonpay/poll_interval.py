"""Poll interval backoff for long-running status checks."""

from __future__ import annotations

TERMINAL_STATUSES = frozenset({"successful", "failed", "cancelled", "completed"})


def is_terminal_transaction_status(status: str) -> bool:
    """True when a status is terminal for resolve/wait continuation."""
    return status in TERMINAL_STATUSES


def resolve_poll_interval_ms(
    *,
    base_interval_ms: int,
    poll_start_time_ms: float,
    now_ms: float | None = None,
) -> int:
    """Poll spacing: 2s base for 2 minutes, then doubles every 2 minutes capped at 15s."""
    import time

    now = now_ms if now_ms is not None else time.time() * 1000
    elapsed = now - poll_start_time_ms
    two_minutes = 2 * 60 * 1000
    if elapsed < two_minutes:
        return base_interval_ms
    periods = int((elapsed - two_minutes) // two_minutes) + 1
    return min(base_interval_ms * (2**periods), 15_000)
