"""Phone number normalization and format validation.

WHY a separate module: phone numbers arrive in many formats
(``+256 700 000 000``, ``+254 710 000 000``, ``0700000000``) but the
payment provider expects digits with the market's calling code. Normalizing
at the SDK boundary means validation, transport, and provider formatting
all operate on the same string.
"""

from __future__ import annotations

import re

_DIAL_BY_CURRENCY = {
    "CDF": "243",
    "KES": "254",
    "RWF": "250",
    "TZS": "255",
    "UGX": "256",
    "XAF": "237",
    "ZMW": "260",
}


_NATIONAL_NUMBER = re.compile(r"\d{9}")


def normalize_phone(phone: str, currency: str = "UGX") -> str:
    """Transform a phone string into digits with the market's calling code.

    Strips whitespace and leading ``+``. A 10-digit number starting with
    ``0`` takes that currency's dial code (UGX 256, KES 254, TZS 255,
    RWF 250, CDF 243, ZMW 260, XAF 237), and so does a 9-digit local
    number typed without its ``0``. Unknown currency uses 256.
    International numbers already carrying a calling code pass through.
    Pure function — transforms but never rejects; pair with
    ``is_valid_phone_format`` for validation.
    """
    normalized = re.sub(r"\s+", "", phone)
    normalized = re.sub(r"^\+", "", normalized)
    dial = _DIAL_BY_CURRENCY.get(currency.upper(), "256")
    if normalized.startswith("0") and len(normalized) == 10:
        normalized = f"{dial}{normalized[1:]}"
    elif _NATIONAL_NUMBER.fullmatch(normalized):
        # A local number typed without its 0; every market uses 9 digits.
        normalized = f"{dial}{normalized}"
    return normalized


def is_valid_phone_format(normalized_phone: str) -> bool:
    """Check that an already-normalized phone contains only 9-15 digits.

    Expects the output of ``normalize_phone`` -- no ``+``, spaces, or
    dashes. The 9-15 range covers all ITU-T E.164 national numbers
    relevant to the SDK's operating regions.
    """
    return re.fullmatch(r"\d{9,15}", normalized_phone) is not None
