"""Unit tests for the transport layer.

Uses ``httpx.MockTransport`` so no real network calls are made. Each test
sets up the mock to return a specific response shape, then asserts the
transport's ``send`` returns the right ``Result`` and the envelope/headers
match the spec.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from nylonpay.signature import create_canonical_payload
from nylonpay.transport import (
    SdkException,
    create_sdk_error,
    create_transport,
    parse_error,
)
from nylonpay.types import SdkError

API_KEY = "npk_test_transport"
API_SECRET = "nps_test_transport_secret"


def _sign(data: dict, secret: str = API_SECRET) -> str:
    return hmac.new(
        secret.encode(),
        create_canonical_payload(data).encode(),
        hashlib.sha256,
    ).hexdigest()


def _bind(request: httpx.Request, data: dict) -> dict:
    """Mimic the backend: echo the request nonce inside the SIGNED data.

    The SDK requires this — it is what proves a response answers the request
    just sent rather than being an older one replayed.
    """
    bound = {**data, "_requestNonce": request.headers.get("x-nylon-nonce", "")}
    return {**bound, "_responseSignature": _sign(bound)}


def _make_client(handler) -> tuple[httpx.Client, dict]:
    """Build a MockTransport-backed httpx.Client. Caller must close."""
    captured: dict = {}

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        try:
            captured["body"] = json.loads(request.content) if request.content else None
        except (ValueError, TypeError):
            captured["body"] = None
        captured["headers"] = dict(request.headers)
        return handler(request)

    transport = httpx.MockTransport(wrapped)
    client = httpx.Client(transport=transport)
    return client, captured


def _build_transport(handler, **overrides) -> tuple[dict, httpx.Client, dict]:
    client, captured = _make_client(handler)
    t = create_transport(
        {
            "api_key": API_KEY,
            "api_secret": API_SECRET,
            "base_url": "https://api.test/services",
            "max_retries": 0,
            "timeout_ms": 1000,
            "http_client": client,
            **overrides,
        }
    )
    return t, client, captured


def test_successful_request_with_valid_signature():
    data = {"foo": "bar", "n": 1}

    def handler(req):
        return httpx.Response(
            200, json={"status": True, "message": "ok", "data": _bind(req, data)}
        )

    t, client, _captured = _build_transport(handler)
    try:
        result = t["send"]({"action": "test-action", "payload": {"x": 1}})
        assert result.is_ok
        assert result.value == data
    finally:
        client.close()


def test_missing_signature_fails_closed():
    def handler(req):
        return httpx.Response(200, json={"status": True, "message": "ok", "data": {"foo": "bar"}})

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "internal"
    finally:
        client.close()


def test_invalid_signature_rejected():
    def handler(req):
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "ok",
                "data": {"foo": "bar", "_responseSignature": "0" * 64},
            },
        )

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "internal"
    finally:
        client.close()


def test_server_error_status_false():
    def handler(req):
        return httpx.Response(
            200,
            json={"status": False, "message": "bad amount -- error-type: validation", "data": None},
        )

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "validation"
        assert "bad amount" in err.message
    finally:
        client.close()


def test_network_error():
    def handler(req):
        raise httpx.ConnectError("dns fail")

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "network"
        assert err.retryable is True
    finally:
        client.close()


def test_timeout_error():
    def handler(req):
        raise httpx.TimeoutException("timed out", request=req)

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "timeout"
        assert err.retryable is True
    finally:
        client.close()


def test_http_500_maps_to_internal():
    def handler(req):
        return httpx.Response(500, json={"message": "boom"})

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "internal"
    finally:
        client.close()


def test_envelope_contains_intent_service_action_fingerprint():
    data = {"foo": "bar"}
    sig = _sign(data)

    def handler(req):
        return httpx.Response(
            200, json={"status": True, "message": "ok", "data": _bind(req, data)}
        )

    t, client, captured = _build_transport(handler)
    try:
        t["send"]({"action": "my-action", "payload": {"a": 1}})
        body = captured["body"]
        assert body["intent"] == "execute"
        assert body["service"] == "sdk"
        assert body["action"] == "my-action"
        assert "_fingerprint" in body["payload"]
        # 64 hex chars
        assert len(body["payload"]["_fingerprint"]) == 64
    finally:
        client.close()


def test_auth_headers_present():
    data = {"foo": "bar"}
    sig = _sign(data)

    def handler(req):
        return httpx.Response(
            200, json={"status": True, "message": "ok", "data": _bind(req, data)}
        )

    t, client, captured = _build_transport(handler)
    try:
        t["send"]({"action": "x", "payload": {"a": 1}})
        h = captured["headers"]
        assert h["x-nylon-key"] == API_KEY
        assert "x-nylon-nonce" in h
        assert len(h["x-nylon-nonce"]) == 32
        assert "x-nylon-timestamp" in h
        assert "x-nylon-signature" in h
        assert len(h["x-nylon-signature"]) == 64
        assert h["content-type"] == "application/json"
    finally:
        client.close()


# parse_error ------------------------------------------------------------------


def test_parse_error_json_format():
    err = parse_error(json.dumps({"category": "validation", "message": "bad", "retryable": False}))
    assert err.category == "validation"
    assert err.message == "bad"
    assert err.retryable is False


def test_parse_error_raw_message_with_suffix():
    err = parse_error("something failed -- error-type: provider")
    assert err.category == "provider"
    assert err.message == "something failed"


def test_parse_error_unknown_falls_back_to_internal():
    err = parse_error("plain message")
    assert err.category == "internal"
    assert err.message == "plain message"


def test_parse_error_json_missing_keys_falls_through_to_suffix():
    err = parse_error(json.dumps({"foo": "bar"}))
    # Not a valid SdkError JSON, no suffix -> internal
    assert err.category == "internal"


# create_sdk_error -------------------------------------------------------------


def test_create_sdk_error_returns_sdk_exception():
    e = SdkError(category="validation", message="bad", retryable=False)
    exc = create_sdk_error(e)
    assert isinstance(exc, SdkException)
    assert exc.category == "validation"
    assert exc.retryable is False
    assert "bad" in str(exc)


# Response size cap ------------------------------------------------------------


def test_oversized_response_rejected_when_content_length_declared():
    """A server declaring an oversized body is rejected up front."""
    from nylonpay import transport as transport_module

    original_cap = transport_module._MAX_RESPONSE_BYTES
    transport_module._MAX_RESPONSE_BYTES = 1024
    try:
        body = b"x" * 4096

        def handler(_request):
            return httpx.Response(200, content=body)

        t, client, _ = _build_transport(handler)
        try:
            result = t["send"]({"action": "collect-payment", "payload": {"amount": 1000}})
        finally:
            client.close()

        assert result.is_err
        assert parse_error(result.error).category == "internal"
    finally:
        transport_module._MAX_RESPONSE_BYTES = original_cap


def test_oversized_response_rejected_without_content_length():
    """The case the old buffered guard missed entirely.

    A chunked response carries no Content-Length, so a header-only check can
    never fire — the body would be read into memory in full regardless. The cap
    must be enforced while reading, from the running byte count.
    """
    from nylonpay import transport as transport_module

    original_cap = transport_module._MAX_RESPONSE_BYTES
    transport_module._MAX_RESPONSE_BYTES = 1024
    try:

        def handler(_request):
            # An iterator body makes httpx stream it — no Content-Length set.
            return httpx.Response(200, content=iter([b"x" * 512] * 8))

        t, client, _ = _build_transport(handler)
        try:
            result = t["send"]({"action": "collect-payment", "payload": {"amount": 1000}})
        finally:
            client.close()

        assert result.is_err
        assert parse_error(result.error).category == "internal"
    finally:
        transport_module._MAX_RESPONSE_BYTES = original_cap


def test_response_under_the_cap_still_succeeds():
    data = {"ok": True}

    def handler(req):
        return httpx.Response(
            200,
            json={"status": True, "message": "", "data": _bind(req, data)},
        )

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "collect-payment", "payload": {"amount": 1000}})
    finally:
        client.close()

    assert result.is_ok


# Response replay binding ------------------------------------------------------


def test_response_without_echoed_nonce_is_rejected():
    """A correctly-signed response that does not name the request it answers
    cannot be told apart from an older response replayed onto this call."""
    data = {"foo": "bar"}

    def handler(_req):
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "ok",
                "data": {**data, "_responseSignature": _sign(data)},
            },
        )

    t, client, _ = _build_transport(handler)
    try:
        result = t["send"]({"action": "x", "payload": {}})
    finally:
        client.close()

    assert result.is_err
    assert parse_error(result.error).category == "internal"


def test_replayed_response_from_an_earlier_request_is_rejected():
    """The actual attack: capture one legitimately-signed response, replay it
    onto a later call. The HMAC still verifies — only the nonce binding catches it."""
    data = {"status": "successful"}
    captured_blob: dict = {}

    def handler(req):
        if not captured_blob:
            # First call: a genuine, correctly-bound response — and we keep it.
            captured_blob.update(_bind(req, data))
        return httpx.Response(
            200, json={"status": True, "message": "ok", "data": captured_blob}
        )

    t, client, _ = _build_transport(handler)
    try:
        first = t["send"]({"action": "get-status", "payload": {}})
        replayed = t["send"]({"action": "get-status", "payload": {}})
    finally:
        client.close()

    assert first.is_ok, "the genuine response must still be accepted"
    assert replayed.is_err, "the replayed blob must not satisfy a later request"
    assert parse_error(replayed.error).category == "internal"
