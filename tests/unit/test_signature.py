"""Unit tests for signature/canonical-payload primitives."""

from __future__ import annotations

import hashlib
import hmac
import re

from nylonpay.signature import (
    create_canonical_payload,
    create_signature,
    create_signature_payload,
    create_timestamp,
)

# create_canonical_payload ----------------------------------------------------


def test_canonical_payload_sorts_top_level_keys():
    a = create_canonical_payload({"b": 1, "a": 2})
    b = create_canonical_payload({"a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1}'


def test_canonical_payload_sorts_nested_keys():
    a = create_canonical_payload({"outer": {"z": 1, "a": 2}, "first": 0})
    b = create_canonical_payload({"first": 0, "outer": {"a": 2, "z": 1}})
    assert a == b
    assert '"a":2,"z":1' in a  # nested sorted


def test_canonical_payload_arrays_preserve_order():
    a = create_canonical_payload([1, 2, 3])
    b = create_canonical_payload([3, 2, 1])
    assert a != b
    assert a == "[1,2,3]"


def test_canonical_payload_no_whitespace():
    out = create_canonical_payload({"a": 1, "b": [1, 2, {"x": 1}]})
    assert " " not in out
    assert "\n" not in out


# create_signature_payload -----------------------------------------------------


def test_signature_payload_dot_format():
    out = create_signature_payload(
        {
            "fingerprint": "fp",
            "nonce": "nc",
            "timestamp": "ts",
            "payload": {"b": 1, "a": 2},
        }
    )
    # canonical of {"b":1,"a":2} = '{"a":2,"b":1}'
    assert out == 'fp.nc.ts.{"a":2,"b":1}'


# create_signature -------------------------------------------------------------


def test_create_signature_is_64_hex():
    sig = create_signature(
        {
            "fingerprint": "fp",
            "nonce": "nc",
            "timestamp": "ts",
            "payload": {"a": 1},
            "secret": "secret",
        }
    )
    assert len(sig) == 64
    assert re.fullmatch(r"[0-9a-f]+", sig) is not None


def test_create_signature_matches_manual_hmac():
    secret = "shh"
    payload = {"b": 2, "a": 1}
    sig = create_signature(
        {
            "fingerprint": "fp",
            "nonce": "nc",
            "timestamp": "ts",
            "payload": payload,
            "secret": secret,
        }
    )
    expected = hmac.new(
        secret.encode(),
        create_signature_payload(
            {"fingerprint": "fp", "nonce": "nc", "timestamp": "ts", "payload": payload}
        ).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected


def test_create_signature_deterministic():
    args = {
        "fingerprint": "fp",
        "nonce": "nc",
        "timestamp": "ts",
        "payload": {"a": 1},
        "secret": "secret",
    }
    assert create_signature(args) == create_signature(args)


def test_create_signature_changes_with_payload():
    base = {"fingerprint": "fp", "nonce": "nc", "timestamp": "ts", "secret": "s"}
    a = create_signature({**base, "payload": {"a": 1}})
    b = create_signature({**base, "payload": {"a": 2}})
    assert a != b


# create_timestamp -------------------------------------------------------------


def test_create_timestamp_is_millisecond_digits():
    ts = create_timestamp()
    assert ts.isdigit()
    assert len(ts) == 13  # epoch ms as of 2024+
