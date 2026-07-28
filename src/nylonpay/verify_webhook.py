"""Webhook signature verification for incoming Nylon Pay webhooks.

Merchants call :func:`verify_webhook_signature` to confirm that a webhook
payload was genuinely sent by Nylon Pay before acting on it. Two checks
must pass: HMAC authenticity over the raw payload bytes, and timestamp
freshness within a configurable tolerance window.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from .slang import Result
from .types import VerifyWebhookInput

DEFAULT_TOLERANCE_SECONDS = 300

DISABLE_FRESHNESS_CHECK = -1
"""Explicit opt-out of the freshness check.

Must be passed deliberately. ``tolerance_seconds=0`` does NOT disable the
check — it means a tolerance of zero seconds, i.e. as strict as it gets, which
in practice rejects almost everything. That is the safe reading: a developer
reaching for ``0`` is asking for maximum strictness, and previously got the
exact opposite (no freshness check at all, silently).
"""


def verify_webhook_signature(input: VerifyWebhookInput) -> bool:
    """Verify that a webhook payload was genuinely sent by Nylon Pay.

    Two checks, both must pass:

    1. **Authenticity** — HMAC-SHA256 over raw payload bytes matches the signature.
    2. **Freshness** — the timestamp inside the signed body is within
       ``tolerance_seconds`` of now (default 300s). ``0`` means a tolerance of
       zero seconds (maximum strictness), NOT "off"; pass
       ``tolerance_seconds=DISABLE_FRESHNESS_CHECK`` to opt out deliberately.

    Returns ``True`` only when both checks pass. Never raises.
    """
    payload_bytes = _decode_payload(input.payload)
    payload_string = payload_bytes.decode("utf-8", errors="replace")

    expected = hmac.new(
        input.secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    # One canonical signature: lowercase hex, byte-for-byte what Nylon Pay
    # sends in `x-nylon-signature`. Any other spelling of the same value —
    # uppercase hex in particular — is rejected rather than normalized, so
    # there is exactly one accepted form and both SDKs agree on it.

    # Length guard before constant-time comparison
    if len(input.signature) != len(expected):
        return False

    if not hmac.compare_digest(input.signature, expected):
        return False

    # Signature authentic — now enforce freshness
    tolerance = (
        input.tolerance_seconds
        if input.tolerance_seconds is not None
        else DEFAULT_TOLERANCE_SECONDS
    )
    if tolerance == DISABLE_FRESHNESS_CHECK:
        return True
    if tolerance < 0:
        return False

    timestamp_ms = _extract_signed_timestamp_ms(payload_string)
    if timestamp_ms is None:
        # Fail closed: valid signature but no verifiable timestamp = indistinguishable from replay
        return False

    current_ms = int(time.time() * 1000)
    age_ms = abs(current_ms - timestamp_ms)
    return age_ms <= tolerance * 1000


def _decode_payload(payload: str | bytes) -> bytes:
    """Ensure payload is bytes for HMAC computation."""
    if isinstance(payload, bytes):
        return payload
    return payload.encode("utf-8")


def _normalize_iso(raw: str) -> str:
    """Make a UTC-suffixed ISO 8601 string parseable on every supported Python.

    Nylon Pay stamps deliveries with JavaScript's ``toISOString()``, which ends
    in ``Z``. ``datetime.fromisoformat`` only learned to accept that in 3.11,
    so on 3.10 — which this package supports — every genuine webhook would
    otherwise fail the freshness check and be rejected as a replay.
    """
    if raw.endswith(("Z", "z")):
        return raw[:-1] + "+00:00"
    return raw


def _extract_signed_timestamp_ms(payload_string: str) -> int | None:
    """Pull the signed ``timestamp`` out of a verified webhook body.

    Returns epoch milliseconds, or ``None`` when the body is not JSON or
    carries no parseable timestamp. Accepts numbers (epoch seconds or ms)
    and ISO 8601 strings.
    """
    parse_result = Result.try_(lambda: json.loads(payload_string))
    if parse_result.is_err:
        return None
    parsed = parse_result.value

    if not isinstance(parsed, dict):
        return None

    raw = parsed.get("timestamp")

    if isinstance(raw, (int, float)):
        # Values below ~1e12 are seconds, above are milliseconds
        return int(raw * 1000) if raw < 1e12 else int(raw)

    if isinstance(raw, str):
        # Try numeric string first (e.g., "1718976000") — the backend
        # may send the timestamp as a stringified number.
        num_result = Result.try_(lambda: float(raw))
        if num_result.is_ok:
            num = num_result.value
            return int(num * 1000) if num < 1e12 else int(num)
        # Try ISO 8601
        dt_result = Result.try_(lambda: datetime.fromisoformat(_normalize_iso(raw)))
        if dt_result.is_ok:
            dt = dt_result.value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        return None

    return None
