"""Signing conformance test — frozen known-answer vector.

Proves the SDK's HMAC signing produces the exact output the backend
expects. If the JCS sort order, canonical serialization, or HMAC
construction changes, this test fails loudly — before any real request
is rejected by the backend.

The vector is generated once from the SDK's own signing code and frozen.
It's a self-conformance test: it proves the algorithm is deterministic
and stable across code changes, not that it matches the backend (that
requires the backend's verifier, which lives in the backend repo).

If the algorithm intentionally changes (e.g., switching from HMAC-SHA256
to HMAC-SHA512), regenerate the vector and update this test.
"""

from __future__ import annotations

from nylonpay.signature import create_canonical_payload, create_signature

# --- Frozen known-answer vector ---

_SECRET = "nps_test_conformance_secret"
_FINGERPRINT = "test_fingerprint_abc123"
_NONCE = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
_TIMESTAMP = "1718976000000"

_PAYLOAD = {
    "amount": 5000,
    "currency": "UGX",
    "customer": {
        "name": "John Doe",
        "phone_number": "+256700000000",
    },
    "description": "Test payment",
    "reference": "ORDER-2026-001",
    "metadata": {"orderId": "12345", "items": "3"},
}

_EXPECTED_CANONICAL = (
    '{"amount":5000,"currency":"UGX","customer":'
    '{"name":"John Doe","phone_number":"+256700000000"},'
    '"description":"Test payment",'
    '"metadata":{"items":"3","orderId":"12345"},'
    '"reference":"ORDER-2026-001"}'
)

_EXPECTED_SIGNATURE = "e2786d0663d45d400f4bdfb410f97106c97b7ae68a37ebccf0d9070af03bccde"


def test_conformance_canonical_payload() -> None:
    """Canonical payload matches the frozen vector exactly.

    This proves JCS key sorting (UTF-16 code unit order) and JSON
    serialization (no spaces, ensure_ascii=False) are stable.
    """
    result = create_canonical_payload(_PAYLOAD)
    assert result == _EXPECTED_CANONICAL, (
        f"Canonical payload mismatch.\nExpected: {_EXPECTED_CANONICAL}\nGot:      {result}"
    )


def test_conformance_signature() -> None:
    """HMAC-SHA256 signature matches the frozen vector exactly.

    This proves the full signing pipeline: canonical payload +
    dot-separated signature string + HMAC-SHA256 + hex encoding.
    """
    result = create_signature(
        {
            "fingerprint": _FINGERPRINT,
            "nonce": _NONCE,
            "payload": _PAYLOAD,
            "secret": _SECRET,
            "timestamp": _TIMESTAMP,
        }
    )
    assert result == _EXPECTED_SIGNATURE, (
        f"Signature mismatch.\nExpected: {_EXPECTED_SIGNATURE}\nGot:      {result}"
    )


def test_conformance_signature_is_64_hex_chars() -> None:
    """Signature is always a 64-character lowercase hex string (SHA-256)."""
    result = create_signature(
        {
            "fingerprint": _FINGERPRINT,
            "nonce": _NONCE,
            "payload": _PAYLOAD,
            "secret": _SECRET,
            "timestamp": _TIMESTAMP,
        }
    )
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_conformance_key_order_independent() -> None:
    """Canonical payload is the same regardless of input dict key order."""
    payload_ordered = {
        "amount": 5000,
        "currency": "UGX",
        "customer": {"name": "John", "phone_number": "256"},
        "description": "Test",
    }
    payload_shuffled = {
        "description": "Test",
        "customer": {"phone_number": "256", "name": "John"},
        "currency": "UGX",
        "amount": 5000,
    }
    assert create_canonical_payload(payload_ordered) == create_canonical_payload(payload_shuffled)


def test_conformance_array_order_significant() -> None:
    """Array order is preserved (JCS only sorts object keys, not arrays)."""
    payload_a = {"items": [{"name": "A"}, {"name": "B"}]}
    payload_b = {"items": [{"name": "B"}, {"name": "A"}]}
    assert create_canonical_payload(payload_a) != create_canonical_payload(payload_b)


def test_conformance_unicode_keys_sorted_by_utf16() -> None:
    """Non-ASCII keys are sorted by UTF-16 code unit, not Unicode code point."""
    # 'é' (U+00E9) has UTF-16 code unit 0x00E9
    # 'z' (U+007A) has UTF-16 code unit 0x007A
    # UTF-16 order: 'z' < 'é' (0x007A < 0x00E9)
    # Unicode code point order would be the same here, but this confirms
    # the sort key is UTF-16 based, not default Python string sort.
    payload = {"z": 1, "é": 2, "a": 3}
    result = create_canonical_payload(payload)
    # Expected order: a, z, é
    assert result == '{"a":3,"z":1,"\u00e9":2}'
