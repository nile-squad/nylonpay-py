"""Constants and defaults for the Nylon Pay SDK.

These values define the SDK's operational envelope — timeouts, retry limits,
polling cadence, and validation thresholds. They're derived from the SDK
spec (v1.3.0) which sets these as cross-language invariants: every SDK
implementation (TypeScript, Python, future languages) must enforce the same
minimums and defaults so backend behavior is predictable regardless of
which language the merchant integrates with.

Defaults are overridable via ``NylonPayConfig`` — merchants with slow
networks or long-running payment flows can widen timeouts and poll limits
without touching the spec-mandated validation thresholds (min amounts,
reference length).
"""

from __future__ import annotations

# --- Defaults (overridable via NylonPayConfig) ---

DEFAULT_BASE_URL = "https://api.nylonpay.nilesquad.com/api/services"
DEFAULT_TIMEOUT_MS = 90_000
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_POLL_INTERVAL_MS = 2_000
DEFAULT_MAX_POLL_DURATION_MS = None
DEFAULT_MAX_POLL_ATTEMPTS = None

POLL_JITTER_MS = 250

# --- Internal constants ---

SDK_SERVICE = "sdk"

SDK_ACTIONS = {
    "collect_payment": "sdk-collect-payment",
    "collect_payment_and_resolve": "sdk-collect-payment-and-resolve",
    "make_payout": "sdk-make-payout",
    "make_payout_and_resolve": "sdk-make-payout-and-resolve",
    "get_status": "sdk-get-status",
    "get_transaction": "sdk-get-transaction",
    "list_transactions": "sdk-list-transactions",
    "verify_phone": "sdk-verify-phone",
    "create_invoice": "sdk-create-invoice",
}

RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

# --- Validation constants ---

MIN_COLLECTION_AMOUNT = 500
MIN_DISBURSEMENT_AMOUNT = 5000
