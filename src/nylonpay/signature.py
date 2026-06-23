"""HMAC signing and JCS-compatible canonical payload serialization.

WHY canonical serialization matters: the backend independently computes
the same HMAC over the request body. Any key-ordering difference between
Python's ``json.dumps`` and JavaScript's ``JSON.stringify`` would
produce mismatched signatures and reject every request. RFC 8785 (JCS)
mandates sorting by UTF-16 code unit order — matching JavaScript's
``<`` operator on strings.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


def _sort_value(value: Any) -> Any:
    """Recursively sort dict keys by UTF-16 code unit order.

    Arrays preserve their original order (JCS only sorts object keys).
    Non-container values pass through unchanged.
    """
    if isinstance(value, list):
        return [_sort_value(entry) for entry in value]
    if isinstance(value, dict):
        sorted_items = sorted(
            value.items(),
            key=lambda kv: kv[0].encode("utf-16-le"),
        )
        return {k: _sort_value(v) for k, v in sorted_items}
    return value


def create_canonical_payload(payload: Any) -> str:
    """Serialize ``payload`` to a deterministic JSON string.

    Keys are sorted by UTF-16 code unit order (RFC 8785 JCS) so the
    output is byte-identical to the backend's verification — both
    sides must produce the same JSON string or the HMAC won't match.
    """
    return json.dumps(_sort_value(payload), separators=(",", ":"), ensure_ascii=False)


def create_signature_payload(input: dict[str, Any]) -> str:
    """Build the dot-separated string that gets HMAC-signed.

    Binds fingerprint, nonce, timestamp, and canonical payload into a
    single string so the signature covers all four — preventing any
    one field from being swapped without invalidating the signature.
    """
    fingerprint: str = input["fingerprint"]
    nonce: str = input["nonce"]
    timestamp: str = input["timestamp"]
    payload: Any = input["payload"]
    canonical = create_canonical_payload(payload)
    return f"{fingerprint}.{nonce}.{timestamp}.{canonical}"


def create_signature(input: dict[str, Any]) -> str:
    """Compute HMAC-SHA256 over the signature payload.

    The secret is the merchant's API secret. The output is a lowercase
    hex string that the backend verifies with constant-time comparison.
    """
    fingerprint: str = input["fingerprint"]
    nonce: str = input["nonce"]
    payload: Any = input["payload"]
    secret: str = input["secret"]
    timestamp: str = input["timestamp"]

    sig_payload = create_signature_payload(
        {
            "fingerprint": fingerprint,
            "nonce": nonce,
            "payload": payload,
            "timestamp": timestamp,
        }
    )
    return hmac.new(
        secret.encode(),
        sig_payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_timestamp() -> str:
    """Return the current time as a millisecond-precision string.

    The backend enforces a freshness window on this value to limit
    replay-attack exposure. Millisecond precision matches JavaScript's
    ``Date.now()``.
    """
    return str(int(time.time() * 1000))
