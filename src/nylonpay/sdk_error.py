"""Map wire categories onto the merchant-facing ALL-CAPS reason."""

from __future__ import annotations

from typing import Any

from .config import (
    UNREACHABLE_CODE,
    UNREACHABLE_HOST_OFFLINE,
    UNREACHABLE_NYLON_DOWN,
)
from .types import SdkError, SdkErrorCategory, SdkErrorReason

REASON_SET: frozenset[str] = frozenset(
    {
        "AUTH",
        "VALIDATION",
        "LIMIT",
        "RATE_LIMIT",
        "ACCOUNT",
        "PROVIDER",
        "DUPLICATE",
        "NOT_FOUND",
        "INTERNAL",
        "NETWORK",
        "SERVICES_DOWN",
        "TIMEOUT",
    }
)

CATEGORY_TO_REASON: dict[str, SdkErrorReason] = {
    "auth": "AUTH",
    "validation": "VALIDATION",
    "limit": "LIMIT",
    "rate_limit": "RATE_LIMIT",
    "account": "ACCOUNT",
    "provider": "PROVIDER",
    "duplicate": "DUPLICATE",
    "not_found": "NOT_FOUND",
    "internal": "INTERNAL",
    "network": "NETWORK",
    "timeout": "TIMEOUT",
}

REASON_TO_CATEGORY: dict[str, SdkErrorCategory] = {
    "AUTH": "auth",
    "VALIDATION": "validation",
    "LIMIT": "limit",
    "RATE_LIMIT": "rate_limit",
    "ACCOUNT": "account",
    "PROVIDER": "provider",
    "DUPLICATE": "duplicate",
    "NOT_FOUND": "not_found",
    "INTERNAL": "internal",
    "NETWORK": "network",
    "SERVICES_DOWN": "network",
    "TIMEOUT": "timeout",
}

OUTCOME_CODE_TO_REASON: dict[str, SdkErrorReason] = {}


def resolve_reason(
    *,
    reason: str | None = None,
    category: str | None = None,
    message: str,
    code: str | None = None,
) -> SdkErrorReason:
    if reason in REASON_SET:
        return reason  # ty: ignore[invalid-return-type]
    if code and code in OUTCOME_CODE_TO_REASON:
        return OUTCOME_CODE_TO_REASON[code]
    if code == UNREACHABLE_CODE or message == UNREACHABLE_HOST_OFFLINE:
        if message == UNREACHABLE_HOST_OFFLINE:
            return "NETWORK"
        if message == UNREACHABLE_NYLON_DOWN:
            return "SERVICES_DOWN"
    if message == UNREACHABLE_NYLON_DOWN:
        return "SERVICES_DOWN"
    if category in CATEGORY_TO_REASON:
        return CATEGORY_TO_REASON[category]
    return "INTERNAL"


def build_sdk_error(
    *,
    reason: str | None = None,
    category: str | None = None,
    message: str,
    retryable: bool | None = None,
    code: str | None = None,
) -> SdkError:
    resolved = resolve_reason(
        reason=reason, category=category, message=message, code=code
    )
    resolved_category = REASON_TO_CATEGORY[resolved]
    resolved_code = code
    if resolved_code is None and resolved in {"NETWORK", "SERVICES_DOWN"}:
        resolved_code = UNREACHABLE_CODE
    return SdkError(
        reason=resolved,
        message=message,
        retryable=retryable,
        category=resolved_category,
        code=resolved_code,
    )


def error_to_dict(error: SdkError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason": error.reason,
        "category": error.category,
        "message": error.message,
    }
    if error.retryable is not None:
        payload["retryable"] = error.retryable
    if error.code is not None:
        payload["code"] = error.code
    return payload
