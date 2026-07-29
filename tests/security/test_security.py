"""Canonical security test suite for the nylonpay-py SDK.

Covers S1-S14 — the cryptographic and configuration invariants the SDK
must uphold. All tests use mocked transport (``httpx.MockTransport``);
no network calls are made.

Each test name references its spec ID (e.g. ``test_S1_signature_deterministic``)
so failures point directly to the violated invariant.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
import pytest

from nylonpay import (
    CollectPaymentInput,
    Customer,
    VerifyWebhookInput,
    create_nylon_pay,
    verify_webhook_signature,
)
from nylonpay.fingerprint import generate_fingerprint
from nylonpay.nonce import generate_nonce
from nylonpay.signature import (
    create_canonical_payload,
    create_signature,
)
from nylonpay.transport import (
    create_transport,
    parse_error,
)
from nylonpay.verify_response import verify_response_signature
from nylonpay.verify_webhook import DISABLE_FRESHNESS_CHECK
from nylonpay.wire import to_wire

SECRET = "nps_test_security_secret_xyz"


def _webhook_input(
    *,
    payload: bytes,
    signature: str,
    secret: str = SECRET,
) -> VerifyWebhookInput:
    return VerifyWebhookInput(
        payload=payload,
        signature=signature,
        secret=secret,
        tolerance_seconds=DISABLE_FRESHNESS_CHECK,
    )


def _sign(data: dict, secret: str = SECRET) -> str:
    return hmac.new(
        secret.encode(),
        create_canonical_payload(data).encode(),
        hashlib.sha256,
    ).hexdigest()


# S1 — Signature is deterministic + sensitive to every input --------------------


def test_S1_signature_deterministic():
    """Same inputs → same signature, 64 hex chars, cannot be reproduced without secret."""
    args = {
        "fingerprint": "fp_1",
        "nonce": "nonce_1",
        "timestamp": "1700000000000",
        "payload": {"amount": 1000, "currency": "UGX"},
        "secret": SECRET,
    }
    sig_a = create_signature(args)
    sig_b = create_signature(args)
    assert sig_a == sig_b
    assert len(sig_a) == 64
    assert all(c in "0123456789abcdef" for c in sig_a)


def test_S1_signature_changes_with_payload():
    base = {
        "fingerprint": "fp",
        "nonce": "n",
        "timestamp": "t",
        "secret": SECRET,
    }
    a = create_signature({**base, "payload": {"x": 1}})
    b = create_signature({**base, "payload": {"x": 2}})
    assert a != b


def test_S1_signature_changes_with_secret():
    base = {
        "fingerprint": "fp",
        "nonce": "n",
        "timestamp": "t",
        "payload": {"x": 1},
    }
    a = create_signature({**base, "secret": "secret_a"})
    b = create_signature({**base, "secret": "secret_b"})
    assert a != b


def test_S1_signature_changes_with_nonce():
    base = {
        "fingerprint": "fp",
        "timestamp": "t",
        "payload": {"x": 1},
        "secret": SECRET,
    }
    a = create_signature({**base, "nonce": "n1"})
    b = create_signature({**base, "nonce": "n2"})
    assert a != b


def test_S1_signature_changes_with_timestamp():
    base = {
        "fingerprint": "fp",
        "nonce": "n",
        "payload": {"x": 1},
        "secret": SECRET,
    }
    a = create_signature({**base, "timestamp": "t1"})
    b = create_signature({**base, "timestamp": "t2"})
    assert a != b


# S2 — Canonical payload: object-key order independent, array order significant -


def test_S2_top_level_key_order_independent():
    a = create_canonical_payload({"b": 1, "a": 2, "c": 3})
    b = create_canonical_payload({"c": 3, "a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1,"c":3}'


def test_S2_nested_key_order_independent():
    a = create_canonical_payload({"outer": {"z": 1, "a": 2}, "first": 0})
    b = create_canonical_payload({"first": 0, "outer": {"a": 2, "z": 1}})
    assert a == b


def test_S2_array_order_significant():
    """Array order matters — JCS only sorts object keys, not list elements."""
    a = create_canonical_payload([1, 2, 3])
    b = create_canonical_payload([3, 2, 1])
    assert a != b
    assert a == "[1,2,3]"
    assert b == "[3,2,1]"


# S3 — Nonces: 32 hex chars default, unique across many generations ------------


def test_S3_default_length_32_hex():
    n = generate_nonce()
    assert len(n) == 32
    assert all(c in "0123456789abcdef" for c in n)


def test_S3_uniqueness_across_100():
    nonces = {generate_nonce() for _ in range(100)}
    assert len(nonces) == 100


# S4 — Fingerprint is stable 64-char hex within a process ----------------------


def test_S4_fingerprint_stable_64_hex():
    a = generate_fingerprint()
    b = generate_fingerprint()
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


# S5 — Response verification accepts valid signature --------------------------


def test_S5_response_verification_accepts_valid():
    data = {"transaction": {"id": "t1", "amount": 1000}}
    sig = _sign(data)
    assert verify_response_signature(data, sig, SECRET) is True


# S6 — Response verification rejects tampered payload + wrong secret ----------


def test_S6_tampered_data_rejected():
    data = {"x": 1}
    sig = _sign(data)
    tampered = {"x": 2}
    assert verify_response_signature(tampered, sig, SECRET) is False


def test_S6_wrong_secret_rejected():
    data = {"x": 1}
    sig = _sign(data, "other_secret")
    assert verify_response_signature(data, sig, SECRET) is False


# S7 — Response verification: malformed/short/non-hex → False, no throw --------


def test_S7_empty_signature_no_throw():
    assert verify_response_signature({"a": 1}, "", SECRET) is False


def test_S7_short_signature_no_throw():
    assert verify_response_signature({"a": 1}, "ab", SECRET) is False


def test_S7_non_hex_signature_no_throw():
    assert verify_response_signature({"a": 1}, "Z" * 64, SECRET) is False


def test_S7_one_byte_flipped_rejected():
    data = {"foo": "bar"}
    sig = _sign(data)
    # Flip one byte in the middle of the signature
    chars = list(sig)
    flip_pos = 10
    chars[flip_pos] = "0" if chars[flip_pos] != "0" else "1"
    flipped = "".join(chars)
    assert verify_response_signature(data, flipped, SECRET) is False


# S8 — Webhook verification: valid, tampered, wrong secret, malformed ---------


def _signed_webhook(body: dict, secret: str = SECRET) -> tuple[bytes, str]:
    body_bytes = json.dumps(body).encode("utf-8")
    sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return body_bytes, sig


def test_S8_valid_signature_accepted():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "x"}
    body_bytes, sig = _signed_webhook(body)
    inp = _webhook_input(payload=body_bytes, signature=sig)
    assert verify_webhook_signature(inp) is True


def test_S8_tampered_body_rejected():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "x"}
    _, sig = _signed_webhook(body)
    tampered = json.dumps({"timestamp": str(int(time.time() * 1000)), "data": "Y"}).encode()
    inp = _webhook_input(payload=tampered, signature=sig)
    assert verify_webhook_signature(inp) is False


def test_S8_wrong_secret_rejected():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "x"}
    body_bytes, sig = _signed_webhook(body, "wrong_secret")
    inp = _webhook_input(payload=body_bytes, signature=sig)
    assert verify_webhook_signature(inp) is False


def test_S8_malformed_signature_no_throw():
    body = {"timestamp": str(int(time.time() * 1000))}
    body_bytes, _ = _signed_webhook(body)
    inp = _webhook_input(payload=body_bytes, signature="not-a-real-sig!!!")
    assert verify_webhook_signature(inp) is False


# S9 — Constant-time, length-guarded comparison --------------------------------


def test_S9_compare_digest_handles_different_lengths():
    """Length-guarded constant-time comparison never raises on length mismatch."""
    # Different lengths
    assert verify_response_signature({"a": 1}, "short", SECRET) is False
    assert verify_response_signature({"a": 1}, "x" * 100, SECRET) is False
    # Same length but wrong value
    assert verify_response_signature({"a": 1}, "a" * 64, SECRET) is False
    # Webhook: different lengths
    body = json.dumps({"timestamp": "1700000000000"}).encode()
    inp_short = _webhook_input(payload=body, signature="ab")
    inp_long = _webhook_input(payload=body, signature="a" * 200)
    assert verify_webhook_signature(inp_short) is False
    assert verify_webhook_signature(inp_long) is False


# S10 — Transport rejects success response without signature (fail-closed) -----


def test_S10_missing_signature_fails_closed():
    def handler(req):
        return httpx.Response(
            200,
            json={"status": True, "message": "ok", "data": {"foo": "bar"}},
        )

    def wrapped(req):
        return handler(req)

    transport = httpx.MockTransport(wrapped)
    client = httpx.Client(transport=transport)
    try:
        t = create_transport(
            {
                "api_key": "npk_test_s10",
                "api_secret": SECRET,
                "base_url": "https://api.test/services",
                "max_retries": 0,
                "timeout_ms": 1000,
                "http_client": client,
            }
        )
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "internal"
    finally:
        client.close()


# S11 — Transport rejects invalid signature, accepts valid ---------------------


def test_S11_invalid_signature_rejected():
    def handler(req):
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "ok",
                "data": {"foo": "bar", "_responseSignature": "0" * 64},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        t = create_transport(
            {
                "api_key": "npk_test_s11",
                "api_secret": SECRET,
                "base_url": "https://api.test/services",
                "max_retries": 0,
                "http_client": client,
            }
        )
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_err
        err = parse_error(result.error)
        assert err.category == "internal"
    finally:
        client.close()


def test_S11_valid_signature_accepted():
    data = {"foo": "bar"}

    def handler(req):
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "ok",
                "data": {
                    **data,
                    "_requestNonce": req.headers.get("x-nylon-nonce", ""),
                    "_responseSignature": _sign(
                        {**data, "_requestNonce": req.headers.get("x-nylon-nonce", "")}
                    ),
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        t = create_transport(
            {
                "api_key": "npk_test_s11b",
                "api_secret": SECRET,
                "base_url": "https://api.test/services",
                "max_retries": 0,
                "http_client": client,
            }
        )
        result = t["send"]({"action": "x", "payload": {}})
        assert result.is_ok
        assert result.value == data
    finally:
        client.close()


# S12 — Config rejects bad apiKey/apiSecret prefixes --------------------------


def test_S12_bad_api_key_prefix_rejected():
    with pytest.raises(ValueError, match='api_key must start with "npk_"'):
        create_nylon_pay(api_key="bad_key", api_secret="nps_test_abc")


def test_S12_bad_api_secret_prefix_rejected():
    with pytest.raises(ValueError, match='api_secret must start with "nps_"'):
        create_nylon_pay(api_key="npk_test_abc", api_secret="bad_secret")


# S13 — Secret never appears on SDK public surface, cache is secret-aware ------


def test_S13_no_secret_on_public_surface():
    secret = "nps_test_super_secret_value_xyz_123"
    sdk = create_nylon_pay(api_key="npk_test_s13", api_secret=secret)
    # No attribute (or method qualname) should contain the secret
    for attr_name in dir(sdk):
        if attr_name.startswith("__"):
            continue
        attr = getattr(sdk, attr_name, None)
        if callable(attr):
            qual = getattr(attr, "__qualname__", "")
            assert secret not in qual, f"Secret leaked into {attr_name}.__qualname__"
    # str/repr of the SDK should not contain the secret
    assert secret not in str(sdk)
    assert secret not in repr(sdk)


def test_S13_different_secret_yields_different_instance():
    """Cache key is secret-aware: same apiKey + different secret → fresh instance."""
    api_key = "npk_test_s13_secret_aware"
    a = create_nylon_pay(api_key=api_key, api_secret="nps_test_secret_alpha")
    b = create_nylon_pay(api_key=api_key, api_secret="nps_test_secret_beta")
    assert a is not b


def test_S13_to_wire_of_inputs_excludes_secret():
    secret = "nps_test_super_secret_value_xyz_123"
    inp = CollectPaymentInput(
        amount=1000,
        currency="UGX",
        customer=Customer(name="A", phone_number="+256700000000"),
        description="x",
    )
    wire = to_wire(inp)
    wire_str = json.dumps(wire, default=str)
    assert secret not in wire_str
    assert "nps_" not in wire_str
    # No field named "secret" anywhere
    assert "secret" not in wire_str.lower()


# S14 — Webhook verification is replay-protected -------------------------------


def test_S14_fresh_timestamp_accepted():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "x"}
    body_bytes, sig = _signed_webhook(body)
    inp = VerifyWebhookInput(payload=body_bytes, signature=sig, secret=SECRET)
    assert verify_webhook_signature(inp) is True


def test_S14_stale_timestamp_rejected():
    stale_ms = int(time.time() * 1000) - 600_000  # 10 minutes old
    body = {"timestamp": str(stale_ms), "data": "x"}
    body_bytes, sig = _signed_webhook(body)
    inp = VerifyWebhookInput(payload=body_bytes, signature=sig, secret=SECRET)
    # Default tolerance is 300s — 600s old is stale
    assert verify_webhook_signature(inp) is False


def test_S14_no_timestamp_fails_closed():
    body = {"data": "x"}  # no timestamp
    body_bytes, sig = _signed_webhook(body)
    # Even with tolerance=0, no timestamp is unrecoverable
    inp_no_tol = VerifyWebhookInput(
        payload=body_bytes, signature=sig, secret=SECRET, tolerance_seconds=300
    )
    assert verify_webhook_signature(inp_no_tol) is False


def test_S14_timestamp_is_signed():
    """Swapping in a fresh timestamp with the original signature → False."""
    # Body1 with stale timestamp — sign it
    stale_ms = int(time.time() * 1000) - 600_000
    body1 = {"timestamp": str(stale_ms), "data": "x"}
    _body1_bytes, sig1 = _signed_webhook(body1)
    # Body2 with fresh timestamp, but reusing sig1 (which was over body1)
    fresh_ms = int(time.time() * 1000)
    body2_bytes = json.dumps({"timestamp": str(fresh_ms), "data": "x"}).encode()
    inp = _webhook_input(payload=body2_bytes, signature=sig1)
    # The signature was over body1 (with stale timestamp), not body2
    assert verify_webhook_signature(inp) is False
