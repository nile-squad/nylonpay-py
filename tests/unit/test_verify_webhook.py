"""Unit tests for webhook signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from nylonpay.types import VerifyWebhookInput
from nylonpay.verify_webhook import (
    DISABLE_FRESHNESS_CHECK,
    verify_webhook_signature,
)

SECRET = "whsec_test_xyz"


def _sign_raw(payload: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _make_input(
    body: dict, secret: str = SECRET, tolerance: int | None = None
) -> VerifyWebhookInput:
    body_bytes = json.dumps(body).encode("utf-8")
    sig = _sign_raw(body_bytes, secret)
    return VerifyWebhookInput(
        payload=body_bytes, signature=sig, secret=secret, tolerance_seconds=tolerance
    )


# Fresh + tampered + wrong secret + malformed ---------------------------------


def test_valid_signature_fresh_timestamp():
    body = {"timestamp": str(int(time.time() * 1000)), "event": "collection.completed"}
    assert verify_webhook_signature(_make_input(body)) is True


def test_tampered_body_rejected():
    body = {"timestamp": str(int(time.time() * 1000)), "event": "collection.completed"}
    inp = _make_input(body)
    # Tamper with payload bytes
    inp_tampered = VerifyWebhookInput(
        payload=b'{"timestamp":"' + str(int(time.time() * 1000)).encode() + b'","event":"X"}',
        signature=inp.signature,
        secret=inp.secret,
    )
    assert verify_webhook_signature(inp_tampered) is False


def test_wrong_secret_rejected():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "foo"}
    sig = _sign_raw(json.dumps(body).encode(), "other_secret")
    inp = VerifyWebhookInput(payload=json.dumps(body), signature=sig, secret=SECRET)
    assert verify_webhook_signature(inp) is False


def test_malformed_signature_no_throw():
    body = {"timestamp": str(int(time.time() * 1000))}
    inp = VerifyWebhookInput(payload=json.dumps(body), signature="not-hex!!!", secret=SECRET)
    # No throw, returns False
    assert verify_webhook_signature(inp) is False


def test_empty_signature_no_throw():
    body = {"timestamp": str(int(time.time() * 1000))}
    inp = VerifyWebhookInput(payload=json.dumps(body), signature="", secret=SECRET)
    assert verify_webhook_signature(inp) is False


# Freshness ---------------------------------------------------------------------


def test_stale_timestamp_rejected():
    body = {"timestamp": str(int(time.time() * 1000) - 600_000), "data": "foo"}
    # Default tolerance is 300s
    assert verify_webhook_signature(_make_input(body)) is False


def test_no_timestamp_fails_closed():
    body = {"data": "foo"}  # no timestamp
    assert verify_webhook_signature(_make_input(body)) is False


def test_tolerance_zero_means_strict_not_disabled():
    """A developer passing 0 means "strictest", and used to silently get "off"."""
    body = {"timestamp": str(int(time.time() * 1000) - 10_000_000), "data": "foo"}
    assert verify_webhook_signature(_make_input(body, tolerance=0)) is False


def test_disable_sentinel_is_the_deliberate_opt_out():
    body = {"timestamp": str(int(time.time() * 1000) - 10_000_000), "data": "foo"}
    result = verify_webhook_signature(_make_input(body, tolerance=DISABLE_FRESHNESS_CHECK))
    assert result is True


# Timestamp formats -------------------------------------------------------------


def test_numeric_string_timestamp_works():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "foo"}
    assert verify_webhook_signature(_make_input(body)) is True


def test_iso_8601_timestamp_works():
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = {"timestamp": iso, "data": "foo"}
    assert verify_webhook_signature(_make_input(body)) is True


def test_backend_isoformat_with_milliseconds_and_z_works():
    """The exact shape the backend sends: JS toISOString(), e.g.
    '2026-05-30T10:30:15.000Z'.

    datetime.fromisoformat only accepts the trailing 'Z' from Python 3.11 on.
    Without normalization this returns False on 3.10 — a supported version —
    meaning every genuine webhook is rejected as unverifiable.
    """
    iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
    body = {"timestamp": iso, "data": "foo"}
    assert verify_webhook_signature(_make_input(body)) is True


def test_lowercase_z_suffix_works():
    iso = time.strftime("%Y-%m-%dT%H:%M:%S.000z", time.gmtime())
    body = {"timestamp": iso, "data": "foo"}
    assert verify_webhook_signature(_make_input(body)) is True


def test_stale_iso_timestamp_still_rejected():
    """Normalizing 'Z' must not weaken replay protection."""
    stale = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 600))
    body = {"timestamp": stale, "data": "foo"}
    assert verify_webhook_signature(_make_input(body)) is False


# Signature casing --------------------------------------------------------------


def test_uppercase_hex_signature_rejected():
    """One canonical signature form: lowercase hex, exactly as sent.

    The same value spelled in uppercase is rejected rather than normalized,
    so there is one accepted form and both SDKs agree on it.
    """
    body = {"timestamp": str(int(time.time() * 1000)), "data": "foo"}
    body_bytes = json.dumps(body).encode("utf-8")
    inp = VerifyWebhookInput(
        payload=body_bytes,
        signature=_sign_raw(body_bytes).upper(),
        secret=SECRET,
    )
    assert verify_webhook_signature(inp) is False


def test_canonical_lowercase_signature_accepted():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "foo"}
    body_bytes = json.dumps(body).encode("utf-8")
    signature = _sign_raw(body_bytes)
    assert signature == signature.lower()
    inp = VerifyWebhookInput(payload=body_bytes, signature=signature, secret=SECRET)
    assert verify_webhook_signature(inp) is True


def test_uppercase_hex_of_wrong_signature_still_rejected():
    body = {"timestamp": str(int(time.time() * 1000)), "data": "foo"}
    body_bytes = json.dumps(body).encode("utf-8")
    inp = VerifyWebhookInput(
        payload=body_bytes,
        signature=_sign_raw(body_bytes, "wrong-secret").upper(),
        secret=SECRET,
    )
    assert verify_webhook_signature(inp) is False


def test_numeric_int_timestamp_works():
    body = {"timestamp": int(time.time() * 1000), "data": "foo"}
    # Sign the JSON-serialized body
    body_bytes = json.dumps(body).encode("utf-8")
    sig = _sign_raw(body_bytes)
    inp = VerifyWebhookInput(payload=body_bytes, signature=sig, secret=SECRET)
    assert verify_webhook_signature(inp) is True


# Bytes vs str payload ---------------------------------------------------------


def test_bytes_payload_works():
    body_bytes = json.dumps({"timestamp": str(int(time.time() * 1000))}).encode("utf-8")
    sig = _sign_raw(body_bytes)
    inp = VerifyWebhookInput(payload=body_bytes, signature=sig, secret=SECRET)
    assert verify_webhook_signature(inp) is True
