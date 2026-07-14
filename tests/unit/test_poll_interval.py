"""Tests for poll interval backoff."""

from __future__ import annotations

from nylonpay.poll_interval import resolve_poll_interval_ms


def test_keeps_base_interval_for_first_two_minutes() -> None:
    assert (
        resolve_poll_interval_ms(
            base_interval_ms=2000,
            poll_start_time_ms=0,
            now_ms=60_000,
        )
        == 2000
    )


def test_doubles_interval_after_two_minutes_up_to_cap() -> None:
    assert (
        resolve_poll_interval_ms(
            base_interval_ms=2000,
            poll_start_time_ms=0,
            now_ms=10 * 60 * 1000,
        )
        == 15_000
    )
