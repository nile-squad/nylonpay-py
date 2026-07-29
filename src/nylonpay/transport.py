"""HTTP transport layer for SDK communication with the Nylon Pay backend.

Handles the Nile envelope format, HMAC request signing, response signature
verification, retries with jittered backoff, and timeouts. The most critical
module in the SDK — every payment operation flows through ``send``.

**Security model:** each request is signed with a fresh nonce, timestamp,
and HMAC-SHA256 over the canonical payload. The backend rejects requests
with stale timestamps (replay protection) or mismatched signatures
(authenticity). Responses are verified the same way — fail-closed (D15):
a missing or invalid ``_responseSignature`` is treated as tampered, never
returned to the caller as success.

**Retry strategy (D19):** the body is built once (the payload — including
the reference idempotency key — is constant across attempts), but each
attempt is signed fresh. This keeps every retry inside the backend's
timestamp-freshness window. Safety against double-processing rests on the
constant reference: the backend replays the existing transaction for a
repeated reference rather than charging again.

**Error encoding:** errors are JSON-serialized ``SdkError`` strings
(category + message + retryable) so merchants can ``parse_error`` to
recover structured data and branch on category instead of parsing
HTTP codes or message text.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any, TypeVar

import httpx

from .config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_MS,
    RETRYABLE_STATUS_CODES,
    SDK_SERVICE,
)
from .fingerprint import generate_fingerprint
from .nonce import generate_nonce
from .signature import create_signature, create_timestamp
from .slang import Err, Ok, Result
from .types import SdkError, SdkErrorCategory
from .verify_response import verify_response_signature

T = TypeVar("T")

# --- Module-level constants ---

_CACHED_FINGERPRINT: str = generate_fingerprint()

_MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024  # 10 MiB — reject oversized responses before parsing

_KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {
        "auth",
        "validation",
        "limit",
        "rate_limit",
        "account",
        "provider",
        "duplicate",
        "not_found",
        "internal",
        "network",
        "timeout",
    }
)

_STATUS_CATEGORY: dict[int, SdkErrorCategory] = {408: "timeout", 429: "rate_limit"}

_ERROR_TYPE_SUFFIX = re.compile(
    r"^(.*?)\s*--\s*error-type:\s*([a-z_]+)\s*$",
    re.DOTALL | re.IGNORECASE,
)


# --- Exception class ---


class SdkException(Exception):
    """Exception thrown by operations on initiation failure.

    Carries ``category`` and ``retryable`` so merchants can catch and branch
    on category without parsing the message.
    """

    def __init__(
        self,
        category: SdkErrorCategory,
        message: str,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


# --- Public functions ---


def create_sdk_error(error: SdkError) -> SdkException:
    """Convert a structured SdkError into a throwable SdkException.

    Used by operations that throw on initiation failure (invalid key,
    etc.) so merchants can ``except SdkException as e`` and read ``e.category``.
    """
    return SdkException(
        category=error.category,
        message=error.message,
        retryable=error.retryable,
    )


def parse_error(error: str) -> SdkError:
    """Parse an error string into a structured SdkError with a category.

    Tries the JSON envelope first (our serialized SdkError format); otherwise
    pulls the server's `` -- error-type: <category>`` suffix off a raw message,
    falling back to category ``internal`` when untagged.
    """
    # Try JSON parse first (our serialized SdkError format)
    parse_result = Result.try_(lambda: json.loads(error))
    if parse_result.is_ok:
        parsed = parse_result.value
        if (
            isinstance(parsed, dict)
            and "category" in parsed
            and "message" in parsed
            and isinstance(parsed["category"], str)
            and isinstance(parsed["message"], str)
        ):
            return SdkError(
                category=parsed["category"],
                message=parsed["message"],
                retryable=parsed.get("retryable"),
            )

    # Raw server message: pull the ` -- error-type: <category>` suffix if present
    category, clean_message = _parse_category_from_message(error)
    return SdkError(
        category=category if category is not None else "internal",
        message=clean_message,
    )


def create_transport(config: dict[str, Any]) -> dict[str, Any]:
    """Create the transport layer for SDK requests.

    Factory returns ``{"send": send, "parse_error": parse_error}`` where
    ``send`` is the synchronous request function bound to the provided credentials
    and configuration.

    The ``http_client`` key accepts an ``httpx.Client`` for testing
    injection — when omitted, a new client is created per call.
    """
    api_key: str = config["api_key"]
    api_secret: str = config["api_secret"]
    base_url: str = config.get("base_url", DEFAULT_BASE_URL)
    timeout_ms: int = config.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    max_retries: int = config.get("max_retries", DEFAULT_MAX_RETRIES)
    http_client: httpx.Client | None = config.get("http_client")

    def send(request: dict[str, Any]) -> Result[Any, str]:
        """Send a request to the backend with retry and signature verification.

        The envelope/body is built once (the payload — including the reference
        idempotency key — is constant across attempts), but each attempt is
        signed fresh: a new nonce, timestamp, and signature per try. This keeps
        every retry inside the backend's timestamp-freshness window and means a
        retry is never rejected as a nonce replay. Safety against double-processing
        rests on the constant reference (D19): the backend replays the existing
        transaction for a repeated reference rather than charging again.
        """
        action: str = request["action"]
        payload: dict[str, Any] = request.get("payload", {})

        envelope = _build_envelope(action=action, payload=payload)
        signed_payload: dict[str, Any] = envelope["payload"]
        body_string: str = json.dumps(envelope)

        timeout = httpx.Timeout(timeout_ms / 1000)
        limits = httpx.Limits(max_keepalive_connections=5)
        owns_client = http_client is None
        client = http_client if http_client is not None else httpx.Client(limits=limits)

        def attempt(current_attempt: int) -> Result[Any, str]:
            # Sign per attempt — fresh nonce/timestamp/signature over the
            # constant payload (D19 invariant).
            headers = _build_auth_headers(
                api_key=api_key,
                api_secret=api_secret,
                payload=signed_payload,
                fingerprint=_CACHED_FINGERPRINT,
            )

            try:
                # Streamed, not buffered: the cap has to be enforced WHILE the
                # body is read. A plain post() reads the whole response into
                # memory before any size check can run, so the guard could only
                # discard an oversized body after already paying its memory
                # cost — and did nothing at all when the server sent no
                # Content-Length (chunked). Reading in chunks with a running
                # total bounds peak memory whatever the server claims.
                with client.stream(
                    "POST",
                    base_url,
                    content=body_string,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    declared_length = response.headers.get("content-length")
                    if declared_length and int(declared_length) > _MAX_RESPONSE_BYTES:
                        sdk_error = SdkError(
                            category="internal",
                            message="Received an invalid response from the server",
                            retryable=False,
                        )
                        return Err(_serialize_error(sdk_error))

                    status_code = response.status_code
                    reason_phrase = response.reason_phrase
                    body_buffer = bytearray()
                    oversized = False
                    for chunk in response.iter_bytes():
                        body_buffer.extend(chunk)
                        if len(body_buffer) > _MAX_RESPONSE_BYTES:
                            # Stop reading immediately — leaving the `with`
                            # block closes the connection mid-body.
                            oversized = True
                            break

                if oversized:
                    sdk_error = SdkError(
                        category="internal",
                        message="Received an invalid response from the server",
                        retryable=False,
                    )
                    return Err(_serialize_error(sdk_error))

                raw_body = bytes(body_buffer)

                if not (200 <= status_code <= 299):
                    retryable = status_code in RETRYABLE_STATUS_CODES

                    error_message = f"HTTP {status_code}"
                    body_result = Result.try_(lambda: json.loads(raw_body))
                    if body_result.is_ok:
                        error_body = body_result.value
                        if isinstance(error_body, dict) and "message" in error_body:
                            error_message = str(error_body["message"])
                    else:
                        error_message = reason_phrase or error_message

                    if retryable and current_attempt < max_retries:
                        backoff = _calculate_backoff(current_attempt)
                        time.sleep(backoff)
                        return attempt(current_attempt + 1)

                    sdk_error = _build_http_error(message=error_message, status_code=status_code)
                    return Err(_serialize_error(sdk_error))

                # Status 200 — parse response body
                response_body = json.loads(raw_body)

                if not isinstance(response_body, dict) or "status" not in response_body:
                    return Err(
                        _serialize_error(
                            SdkError(
                                category="internal",
                                message="Received an invalid response from the server",
                                retryable=False,
                            )
                        )
                    )

                status: bool = response_body["status"]
                message: str = response_body.get("message", "")
                data: Any = response_body.get("data")

                if status is True:
                    stripped_data, response_signature = _strip_response_signature(data)

                    # Fail closed — every authenticated success response from
                    # the backend is signed. Missing signature = tampered or
                    # non-originating response.
                    if response_signature is None:
                        return Err(
                            _serialize_error(
                                SdkError(
                                    category="internal",
                                    message="Could not verify the server response",
                                    retryable=False,
                                )
                            )
                        )

                    is_valid = verify_response_signature(
                        stripped_data, response_signature, api_secret
                    )
                    if not is_valid:
                        return Err(
                            _serialize_error(
                                SdkError(
                                    category="internal",
                                    message="Could not verify the server response",
                                    retryable=False,
                                )
                            )
                        )

                    # The signature proves who produced this; the echoed nonce
                    # proves it answers the request we just sent, and is not an
                    # earlier response replayed. It is signed, so it is as
                    # trustworthy as the signature once the HMAC verifies.
                    unbound_data, echoed_nonce = _strip_request_nonce(stripped_data)
                    if echoed_nonce != headers.get("x-nylon-nonce"):
                        return Err(
                            _serialize_error(
                                SdkError(
                                    category="internal",
                                    message="Could not verify the server response",
                                    retryable=False,
                                )
                            )
                        )

                    return Ok(unbound_data)

                # status === False
                parsed_error = parse_error(message)
                return Err(json.dumps(_error_to_dict(parsed_error)))

            except httpx.TimeoutException:
                sdk_error = SdkError(
                    category="timeout",
                    message="The request timed out",
                    retryable=True,
                )
                if current_attempt < max_retries:
                    backoff = _calculate_backoff(current_attempt)
                    time.sleep(backoff)
                    return attempt(current_attempt + 1)
                return Err(_serialize_error(sdk_error))

            except httpx.HTTPError:
                sdk_error = SdkError(
                    category="network",
                    message=(
                        "Could not reach the server, check your network connection and try again"
                    ),
                    retryable=True,
                )
                if current_attempt < max_retries:
                    backoff = _calculate_backoff(current_attempt)
                    time.sleep(backoff)
                    return attempt(current_attempt + 1)
                return Err(_serialize_error(sdk_error))

        try:
            return attempt(0)
        finally:
            if owns_client:
                client.close()

    return {"send": send, "parse_error": parse_error}


# --- Internal helpers ---


def _build_envelope(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build the Nile request envelope wrapping the operation payload."""
    return {
        "intent": "execute",
        "service": SDK_SERVICE,
        "action": action,
        "payload": {**payload, "_fingerprint": _CACHED_FINGERPRINT},
    }


def _build_auth_headers(
    api_key: str,
    api_secret: str,
    payload: dict[str, Any],
    fingerprint: str,
) -> dict[str, str]:
    """Build auth headers with fresh nonce, timestamp, and signature.

    The signature covers the inner payload (operation input + fingerprint),
    NOT the full Nile envelope — matching the server's verification.
    """
    nonce = generate_nonce()
    timestamp = create_timestamp()
    signature = create_signature(
        {
            "fingerprint": fingerprint,
            "nonce": nonce,
            "timestamp": timestamp,
            "payload": payload,
            "secret": api_secret,
        }
    )

    return {
        "content-type": "application/json",
        "x-nylon-key": api_key,
        "x-nylon-nonce": nonce,
        "x-nylon-signature": signature,
        "x-nylon-timestamp": timestamp,
    }


def _strip_request_nonce(data: Any) -> tuple[Any, str | None]:
    """Strip the echoed ``_requestNonce`` and return it separately.

    Returns ``(data_without_nonce, nonce)``; nonce is ``None`` when the field
    is absent or not a string. The backend signs this value into the response,
    so comparing it against the nonce we sent is what binds a response to the
    request it answers — without it a captured response stays validly signed
    forever and can be replayed to a later call.
    """
    if not isinstance(data, dict) or "_requestNonce" not in data:
        return data, None

    rest = {k: v for k, v in data.items() if k != "_requestNonce"}
    nonce = data.get("_requestNonce")
    return rest, nonce if isinstance(nonce, str) else None


def _strip_response_signature(data: Any) -> tuple[Any, str | None]:
    """Strip ``_responseSignature`` from a payload and return it separately.

    Returns ``(data_without_sig, signature)`` where signature is ``None``
    if the field is absent or not a string.
    """
    if not isinstance(data, dict) or "_responseSignature" not in data:
        return data, None

    response_signature = data.get("_responseSignature")
    if not isinstance(response_signature, str):
        response_signature = None

    stripped = {k: v for k, v in data.items() if k != "_responseSignature"}
    return stripped, response_signature


def _parse_category_from_message(
    message: str,
) -> tuple[SdkErrorCategory | None, str]:
    """Split the server's tagged category off an error message.

    The backend appends `` -- error-type: <category>`` to every SDK error.
    Returns ``(category, clean_message)`` where category is ``None`` if no
    recognized suffix is found.
    """
    match = _ERROR_TYPE_SUFFIX.match(message)
    if match and match.group(2) in _KNOWN_CATEGORIES:
        return match.group(2), match.group(1)  # ty: ignore[invalid-return-type]
    return None, message


def _build_http_error(message: str, status_code: int) -> SdkError:
    """Build a structured SdkError from an HTTP error body's message + status."""
    category, clean_message = _parse_category_from_message(message)

    if category is None:
        category = _STATUS_CATEGORY.get(status_code)
    if category is None:
        category = "internal" if status_code >= 500 else "validation"

    return SdkError(
        category=category,
        message=clean_message,
        retryable=status_code in RETRYABLE_STATUS_CODES,
    )


def _calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay with jitter, in seconds.

    Base doubles each attempt (1s, 2s, 4s...) with up to 500ms random jitter
    to prevent thundering-herd spikes when multiple callers retry simultaneously.
    """
    base = (2**attempt) * 1000
    jitter = random.random() * 500
    return (base + jitter) / 1000


def _serialize_error(error: SdkError) -> str:
    """Serialize an SdkError to a JSON string for Result error values."""
    return json.dumps(_error_to_dict(error))


def _error_to_dict(error: SdkError) -> dict[str, Any]:
    """Convert an SdkError dataclass to a plain dict for JSON serialization."""
    result: dict[str, Any] = {
        "category": error.category,
        "message": error.message,
    }
    if error.retryable is not None:
        result["retryable"] = error.retryable
    return result
