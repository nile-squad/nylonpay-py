"""Unit tests for response signature verification."""

from __future__ import annotations

import hashlib
import hmac

from nylonpay.signature import create_canonical_payload
from nylonpay.verify_response import verify_response_signature

SECRET = "test_secret_xyz"


def _sign(data: dict, secret: str = SECRET) -> str:
    return hmac.new(
        secret.encode(),
        create_canonical_payload(data).encode(),
        hashlib.sha256,
    ).hexdigest()


def test_valid_signature():
    data = {"foo": "bar", "n": 1}
    assert verify_response_signature(data, _sign(data), SECRET) is True


def test_tampered_data():
    data = {"foo": "bar"}
    sig = _sign(data)
    tampered = {"foo": "BAZ"}
    assert verify_response_signature(tampered, sig, SECRET) is False


def test_wrong_secret():
    data = {"foo": "bar"}
    assert verify_response_signature(data, _sign(data, "other"), SECRET) is False


def test_empty_signature():
    assert verify_response_signature({"a": 1}, "", SECRET) is False


def test_short_signature():
    assert verify_response_signature({"a": 1}, "abcd", SECRET) is False


def test_non_hex_signature():
    assert verify_response_signature({"a": 1}, "Z" * 64, SECRET) is False
