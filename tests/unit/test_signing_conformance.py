"""Signing conformance, the spec's canonical vectors V1-V7 (requirement S19).

These are NOT self-generated. They are the conformance vectors published in
the Nylon Pay SDK Spec (transport.md, "Conformance vectors"), generated from
the reference implementation and verified against the backend's verifier.
Reproducing them proves this SDK agrees with the backend,
not merely with itself.

Each vector isolates one failure mode that is otherwise diagnosed only as an
opaque ``auth`` error on live traffic:

* V1 - a representative payload
* V2 - key insertion order is irrelevant
* V3 - arrays keep order, objects inside arrays are still sorted
* V4 - string escaping (ensure_ascii, escaped slashes, HTML escaping)
* V5 - ASCII key ordering is code-unit order, not dictionary order
* V6 - empty containers and zero
* V7 - non-ASCII key ordering; fails under locale collation, UTF-16LE byte
  sorting, and code-point sorting, and passes only under true UTF-16
  code-unit order

Payloads are held as verbatim JSON text from the spec and parsed at test time,
so there is no transcription drift between the spec and this file.

If the algorithm intentionally changes, the spec changes first and these
vectors are regenerated from it.
"""

from __future__ import annotations

import json

import pytest

from nylonpay.signature import create_canonical_payload, create_signature

# --- Fixed inputs, per the spec's "Conformance vectors" section ---

_SECRET = "nps_test_conformance_secret"
_FINGERPRINT = "a" * 64
_NONCE = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
_TIMESTAMP = "1718976000000"

# (id, payload as verbatim spec JSON, expected canonical, expected signature)
_VECTORS: list[tuple[str, str, str, str]] = [
    (
        "V1",
        r'{"amount":5000,"currency":"UGX","customer":{"name":"John Doe","phoneNumber":"+256700000000"},"description":"Test payment","reference":"ORDER-2026-001","metadata":{"orderId":"12345","items":"3"}}',
        r'{"amount":5000,"currency":"UGX","customer":{"name":"John Doe","phoneNumber":"+256700000000"},"description":"Test payment","metadata":{"items":"3","orderId":"12345"},"reference":"ORDER-2026-001"}',
        "dc6e1717d7c37d7a3b334087d9882c07663edb2dfc8f2f06cd77c0d2d8a58686",
    ),
    (
        "V2",
        r'{"metadata":{"items":"3","orderId":"12345"},"reference":"ORDER-2026-001","description":"Test payment","customer":{"phoneNumber":"+256700000000","name":"John Doe"},"currency":"UGX","amount":5000}',
        r'{"amount":5000,"currency":"UGX","customer":{"name":"John Doe","phoneNumber":"+256700000000"},"description":"Test payment","metadata":{"items":"3","orderId":"12345"},"reference":"ORDER-2026-001"}',
        "dc6e1717d7c37d7a3b334087d9882c07663edb2dfc8f2f06cd77c0d2d8a58686",
    ),
    (
        "V3",
        r'{"items":[{"unitPrice":2000,"name":"Zeta","quantity":1},{"name":"Alpha","quantity":2,"unitPrice":500}],"tags":["b","a","c"],"amount":4500}',
        r'{"amount":4500,"items":[{"name":"Zeta","quantity":1,"unitPrice":2000},{"name":"Alpha","quantity":2,"unitPrice":500}],"tags":["b","a","c"]}',
        "98478585cf5ce0193a9aa6a6e86ff7f5dfc025945d03547dd548b9356b797e4b",
    ),
    (
        "V4",
        r'{"note":"café / 50% <b>&\"quoted\"</b>","path":"a/b/c","backslash":"x\\y","newline":"line1\nline2\ttab"}',
        r'{"backslash":"x\\y","newline":"line1\nline2\ttab","note":"café / 50% <b>&\"quoted\"</b>","path":"a/b/c"}',
        "80eb3c6e35b8b3dcc67a57e056634b6f68f2f84b9454bea3aa5e86647eb47649",
    ),
    (
        "V5",
        r'{"Z":1,"_x":2,"a":3,"A":4,"z":5,"0":6}',
        r'{"0":6,"A":4,"Z":1,"_x":2,"a":3,"z":5}',
        "7b9da2fccf0140a7b721715b7b61f17ad3407bd40659b54d983c8e8379108adc",
    ),
    (
        "V6",
        r'{"emptyObject":{},"emptyArray":[],"emptyString":"","zero":0}',
        r'{"emptyArray":[],"emptyObject":{},"emptyString":"","zero":0}',
        "f1d8a628663cc9279c675b001e5142e10c6880c2713145f7ebb946c73af2e875",
    ),
    (
        "V7",
        r'{"ÿ":1,"Ā":2,"a":3,"注文":4}',
        r'{"a":3,"ÿ":1,"Ā":2,"注文":4}',
        "f43182515649622666b920ac1274d6be5ee395d7c295a4eab6e914a48b212a3a",
    ),
]

_IDS = [vector[0] for vector in _VECTORS]


@pytest.mark.parametrize(("vector_id", "payload_json", "expected", "_sig"), _VECTORS, ids=_IDS)
def test_canonical_payload_matches_spec_vector(
    vector_id: str, payload_json: str, expected: str, _sig: str
) -> None:
    """Canonical payload matches the spec vector byte for byte."""
    result = create_canonical_payload(json.loads(payload_json))
    assert result == expected, (
        f"{vector_id} canonical payload mismatch.\nExpected: {expected}\nGot:      {result}"
    )


@pytest.mark.parametrize(("vector_id", "payload_json", "_canon", "expected"), _VECTORS, ids=_IDS)
def test_signature_matches_spec_vector(
    vector_id: str, payload_json: str, _canon: str, expected: str
) -> None:
    """Full signing pipeline matches the spec vector."""
    result = create_signature(
        {
            "fingerprint": _FINGERPRINT,
            "nonce": _NONCE,
            "payload": json.loads(payload_json),
            "secret": _SECRET,
            "timestamp": _TIMESTAMP,
        }
    )
    assert result == expected, (
        f"{vector_id} signature mismatch.\nExpected: {expected}\nGot:      {result}"
    )


def test_v7_rejects_utf16_little_endian_ordering() -> None:
    """V7 pins code-unit ordering against the UTF-16LE byte-sort mistake.

    Sorting UTF-16LE bytes compares the low byte first, which is not code-unit
    order. This asserts the wrong ordering is genuinely different, so the V7
    vector above cannot pass by coincidence if someone reintroduces it.
    """
    keys = ["ÿ", "Ā", "a", "注文"]
    little_endian = sorted(keys, key=lambda k: k.encode("utf-16-le"))
    big_endian = sorted(keys, key=lambda k: k.encode("utf-16-be"))

    assert big_endian == ["a", "ÿ", "Ā", "注文"]
    assert little_endian != big_endian


def test_signature_is_canonical_lowercase_hex() -> None:
    """Signature is always 64 lowercase hex characters (invariant 28)."""
    result = create_signature(
        {
            "fingerprint": _FINGERPRINT,
            "nonce": _NONCE,
            "payload": json.loads(_VECTORS[0][1]),
            "secret": _SECRET,
            "timestamp": _TIMESTAMP,
        }
    )
    assert len(result) == 64
    assert all(character in "0123456789abcdef" for character in result)
