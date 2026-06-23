"""HMAC verification for server responses.

WHY response verification: the backend signs every response with the
merchant's API secret. Verifying the signature before trusting the
data prevents a man-in-the-middle from injecting fake transaction
statuses — a critical safety property for a payments SDK that drives
fulfillment side-effects.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .signature import create_canonical_payload


def verify_response_signature(data: Any, signature: str, secret: str) -> bool:
    """Verify that ``data`` was signed by the backend using ``secret``.

    Uses constant-time comparison to prevent timing side-channels.
    Never raises — returns ``False`` on any mismatch or malformed
    input, so callers can fail-closed without try/except.
    """
    expected_signature = hmac.new(
        secret.encode(),
        create_canonical_payload(data).encode(),
        hashlib.sha256,
    ).hexdigest()

    if len(signature) != len(expected_signature):
        return False

    return hmac.compare_digest(signature, expected_signature)
