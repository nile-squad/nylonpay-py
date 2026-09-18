"""Unit tests for reachability classification and the skip cache."""

from __future__ import annotations

import socket

import httpx

from nylonpay.config import (
    UNREACHABLE_CODE,
    UNREACHABLE_HOST_OFFLINE,
    UNREACHABLE_NYLON_DOWN,
)
from nylonpay.reachability import (
    classify_http_status,
    classify_unreachable,
    create_reachability_tracker,
)
from nylonpay.transport import create_transport, parse_error


def test_dns_failure_is_host_offline() -> None:
    error = httpx.ConnectError("All connection attempts failed")
    error.__cause__ = socket.gaierror(-2, "Name or service not known")
    assert classify_unreachable(error) == UNREACHABLE_HOST_OFFLINE


def test_connection_refused_is_nylon_down() -> None:
    error = httpx.ConnectError("[Errno 111] Connection refused")
    assert classify_unreachable(error) == UNREACHABLE_NYLON_DOWN


def test_gateway_statuses() -> None:
    assert classify_http_status(502) == UNREACHABLE_NYLON_DOWN
    assert classify_http_status(503) == UNREACHABLE_NYLON_DOWN
    assert classify_http_status(400) is None
    assert classify_http_status(500) is None


def test_does_not_check_while_recent_success_is_fresh() -> None:
    now = {"t": 1000.0}
    probes = {"n": 0}

    def probe() -> str | None:
        probes["n"] += 1
        return None

    tracker = create_reachability_tracker(
        now=lambda: now["t"],
        success_fresh_ms=5 * 60 * 1000,
        down_recheck_ms=15_000,
        probe=probe,
    )

    assert tracker["before_send"]() is None
    assert probes["n"] == 0

    tracker["note_up"]()
    now["t"] = 1000.0 + 60_000
    assert tracker["before_send"]() is None
    assert probes["n"] == 0


def test_stale_success_checks_once_then_remembers_the_probe() -> None:
    now = {"t": 1000.0}
    probes = {"n": 0}

    def probe() -> str | None:
        probes["n"] += 1
        return None

    tracker = create_reachability_tracker(
        now=lambda: now["t"],
        success_fresh_ms=5 * 60 * 1000,
        down_recheck_ms=15_000,
        probe=probe,
    )
    tracker["note_up"]()
    now["t"] = 1000.0 + 5 * 60 * 1000 + 1
    assert tracker["before_send"]() is None
    assert probes["n"] == 1
    assert tracker["before_send"]() is None
    assert probes["n"] == 1


def test_tracker_skips_while_down() -> None:
    now = {"t": 1000.0}
    tracker = create_reachability_tracker(
        now=lambda: now["t"],
        success_fresh_ms=5 * 60 * 1000,
        down_recheck_ms=15_000,
    )

    assert tracker["before_send"]() is None
    tracker["note_down"](UNREACHABLE_HOST_OFFLINE)

    blocked = tracker["before_send"]()
    assert blocked is not None and blocked.is_err
    parsed = parse_error(blocked.error)
    assert parsed.category == "network"
    assert parsed.code == UNREACHABLE_CODE
    assert parsed.message == UNREACHABLE_HOST_OFFLINE

    now["t"] = 1000.0 + 15_001
    assert tracker["before_send"]() is None


def test_checks_before_next_call_when_last_failed() -> None:
    now = {"t": 1000.0}
    probes = {"n": 0}

    def probe() -> str:
        probes["n"] += 1
        return UNREACHABLE_NYLON_DOWN

    tracker = create_reachability_tracker(
        now=lambda: now["t"],
        success_fresh_ms=5 * 60 * 1000,
        down_recheck_ms=15_000,
        probe=probe,
    )
    tracker["note_down"](UNREACHABLE_NYLON_DOWN)
    now["t"] = 1000.0 + 15_001
    blocked = tracker["before_send"]()
    assert probes["n"] == 1
    assert blocked is not None and blocked.is_err


def test_hours_old_down_is_not_trusted() -> None:
    now = {"t": 1000.0}
    probes = {"n": 0}

    def probe() -> str | None:
        probes["n"] += 1
        return None

    tracker = create_reachability_tracker(
        now=lambda: now["t"],
        success_fresh_ms=5 * 60 * 1000,
        down_recheck_ms=15_000,
        probe=probe,
    )
    tracker["note_down"](UNREACHABLE_NYLON_DOWN)
    now["t"] = 1000.0 + 6 * 60 * 60 * 1000
    assert tracker["before_send"]() is None
    assert probes["n"] == 1


def test_transport_skips_second_call_after_connect_error() -> None:
    calls = {"n": 0}
    reported = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("Connection refused", request=request)

    transport_http = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport_http)
    try:
        t = create_transport(
            {
                "api_key": "npk_test_transport",
                "api_secret": "nps_test_transport_secret",
                "base_url": "https://api.test/services",
                "max_retries": 0,
                "timeout_ms": 1000,
                "http_client": client,
                "on_error": reported.append,
            }
        )
        first = t["send"]({"action": "sdk-get-status", "payload": {}})
        assert first.is_err
        err = parse_error(first.error)
        assert err.message == UNREACHABLE_NYLON_DOWN
        assert err.code == UNREACHABLE_CODE
        assert len(reported) == 1
        assert reported[0].message == UNREACHABLE_NYLON_DOWN

        second = t["send"]({"action": "sdk-get-status", "payload": {}})
        assert second.is_err
        assert calls["n"] == 1
        assert len(reported) == 2
    finally:
        client.close()
