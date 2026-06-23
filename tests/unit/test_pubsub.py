"""Unit tests for the pubsub event emitter."""

from __future__ import annotations

from nylonpay.pubsub import create_emitter


def test_on_emit_calls_handler():
    e = create_emitter()
    received = []
    e["on"]("ping", lambda d: received.append(d))
    e["emit"]("ping", "hello")
    e["emit"]("ping", "world")
    assert received == ["hello", "world"]


def test_off_removes_handler():
    e = create_emitter()
    received = []

    def h(d):
        received.append(d)

    e["on"]("ping", h)
    e["emit"]("ping", 1)
    e["off"]("ping", h)
    e["emit"]("ping", 2)
    assert received == [1]


def test_off_unregistered_is_noop():
    e = create_emitter()
    e["off"]("missing", lambda d: None)  # no exception


def test_once_fires_only_once():
    e = create_emitter()
    received = []
    e["once"]("ping", lambda d: received.append(d))
    e["emit"]("ping", 1)
    e["emit"]("ping", 2)
    assert received == [1]


def test_error_in_handler_does_not_break_others():
    e = create_emitter()
    received = []
    e["on"]("ping", lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    e["on"]("ping", lambda d: received.append(d))
    e["emit"]("ping", "ok")
    assert received == ["ok"]


def test_unsubscribe_via_returned_function():
    e = create_emitter()
    received = []
    unsub = e["on"]("ping", lambda d: received.append(d))
    e["emit"]("ping", 1)
    unsub()
    e["emit"]("ping", 2)
    assert received == [1]


def test_listener_count():
    e = create_emitter()
    assert e["listener_count"]("ping") == 0
    e["on"]("ping", lambda d: None)
    e["on"]("ping", lambda d: None)
    assert e["listener_count"]("ping") == 2
    assert e["listener_count"]("other") == 0


def test_clear_single_event():
    e = create_emitter()
    e["on"]("a", lambda d: None)
    e["on"]("b", lambda d: None)
    e["clear"]("a")
    assert e["listener_count"]("a") == 0
    assert e["listener_count"]("b") == 1


def test_clear_all_events():
    e = create_emitter()
    e["on"]("a", lambda d: None)
    e["on"]("b", lambda d: None)
    e["clear"]()
    assert e["listener_count"]("a") == 0
    assert e["listener_count"]("b") == 0
