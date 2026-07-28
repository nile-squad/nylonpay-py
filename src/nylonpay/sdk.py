"""SDK instance providing all merchant-facing payment operations.

Created via :func:`factory.create_nylon_pay` and returned as ``NylonPaySdk``.

This module implements the 11 operations in the SDK spec: collect_payment,
collect_payment_and_resolve, make_payout, make_payout_and_resolve,
get_status, get_transaction, list_transactions, get_transactions_by_tag,
verify_phone, create_invoice, and verify_webhook_signature. Each operation
follows the same lifecycle:

1. **Validate** — check input fields (amounts, references, phone format)
   and throw ``SdkException`` on programmer errors before any network call.
2. **Hook (before)** — run the merchant's ``before_*`` hook if registered,
   then re-validate the (possibly mutated) input so hooks can't bypass
   validation (spec invariant #12).
3. **Transport** — sign and send the request via the transport layer.
4. **Hook (after)** — run the merchant's ``after_*`` hook with the result.
5. **Return** — ``PaymentInstance`` for event-driven ops, ``Result`` for
   query/resolve ops.

The validation, hook lifecycle, wire conversion, and error handling are
identical across all SDK implementations per the spec — a merchant porting
from TypeScript to Python gets the same behavior, not a re-interpretation.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from types import SimpleNamespace
from typing import Any, NoReturn, cast

from .coerce import coerce_dataclass
from .config import (
    MIN_COLLECTION_AMOUNT,
    MIN_DISBURSEMENT_AMOUNT,
    SDK_ACTIONS,
)
from .payment import create_payment_instance
from .phone import is_valid_phone_format, normalize_phone
from .poll_interval import is_terminal_transaction_status
from .poll_until_terminal import poll_until_terminal
from .slang import Err, Ok, Result
from .transport import create_sdk_error, create_transport, parse_error
from .types import (
    AfterHookInput,
    CollectPaymentInput,
    CreateInvoiceInput,
    GetStatusInput,
    GetTransactionInput,
    InitiationResult,
    InvoiceResponse,
    ListTransactionsInput,
    ListTransactionsResponse,
    MakePayoutInput,
    NylonPaySdk,
    PaymentInstance,
    PhoneVerification,
    SdkError,
    SdkHooks,
    StatusResponse,
    Transaction,
    TransactionSummary,
    VerifyPhoneInput,
    VerifyWebhookInput,
)
from .verify_webhook import verify_webhook_signature as _verify_webhook_sig
from .wire import from_wire, to_wire

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

UUID_REGEX = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _generate_reference() -> str:
    """Generate a UUID v4 reference for idempotency."""
    return str(uuid.uuid4())


def _throw_validation(message: str) -> NoReturn:
    """Raise a categorised validation error. Never returns."""
    raise create_sdk_error(SdkError(category="validation", message=message))


def _resolve_reference(reference: str | None) -> str:
    """Auto-generate a UUID v4 when *None*, else validate UUID format.

    Uses ``fullmatch``, not ``match``: Python's ``$`` also matches immediately
    before a single trailing newline, so ``re.match`` accepts
    ``"<uuid>\\n"`` — a value the TypeScript SDK's identical-looking regex
    rejects, since JavaScript's ``$`` has no such exception. The reference is a
    cross-language spec contract and is used downstream as an idempotency and
    lookup key, so both SDKs must accept exactly the same set of strings.
    """
    if reference is None:
        return _generate_reference()
    if not re.fullmatch(UUID_REGEX, reference):
        _throw_validation("reference must be a valid UUID")
    return reference


def _validate_collection_amount(amount: int) -> None:
    """Positive integer >= MIN_COLLECTION_AMOUNT."""
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        _throw_validation("amount must be a positive integer")
    if amount < MIN_COLLECTION_AMOUNT:
        _throw_validation(f"Collection amount must be at least {MIN_COLLECTION_AMOUNT} UGX")


def _validate_payout_amount(amount: int) -> None:
    """Positive integer >= MIN_DISBURSEMENT_AMOUNT."""
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        _throw_validation("amount must be a positive integer")
    if amount < MIN_DISBURSEMENT_AMOUNT:
        _throw_validation(f"Payout amount must be at least {MIN_DISBURSEMENT_AMOUNT} UGX")


def _validate_non_empty(value: str, field_name: str) -> None:
    """Non-empty after trim."""
    if not value or not value.strip():
        _throw_validation(f"{field_name} is required")


def _validate_phone_format(normalized_phone: str, field_name: str) -> None:
    """Validate an already-normalized phone via ``is_valid_phone_format``."""
    if not is_valid_phone_format(normalized_phone):
        _throw_validation(f"{field_name} must be a valid phone number")


def _prepare_collect_payload(input: CollectPaymentInput) -> CollectPaymentInput:
    """Full validate + normalize + resolve reference for a collection.

    Run on both the original input and any ``before*`` hook output so a hook
    can never bypass validation (spec invariant #12).
    """
    reference = _resolve_reference(input.reference)
    _validate_collection_amount(input.amount)
    _validate_non_empty(input.customer.name, "customer.name")
    _validate_non_empty(input.customer.phone_number, "customer.phone_number")
    normalized_phone = normalize_phone(input.customer.phone_number)
    _validate_phone_format(normalized_phone, "customer.phone_number")
    _validate_non_empty(input.description, "description")
    if input.method == "bank" and not input.bank:
        _throw_validation('bank details are required when method is "bank"')

    normalized_customer = dataclasses.replace(input.customer, phone_number=normalized_phone)
    return dataclasses.replace(input, reference=reference, customer=normalized_customer)


def _prepare_payout_payload(input: MakePayoutInput) -> MakePayoutInput:
    """Full validate + normalize + resolve reference for a payout.

    Sibling of :func:`_prepare_collect_payload` — same invariant #12 guarantee.
    """
    reference = _resolve_reference(input.reference)
    _validate_payout_amount(input.amount)
    _validate_non_empty(input.customer.name, "customer.name")
    _validate_non_empty(input.customer.phone_number, "customer.phone_number")
    normalized_phone = normalize_phone(input.customer.phone_number)
    _validate_phone_format(normalized_phone, "customer.phone_number")
    _validate_non_empty(input.description, "description")
    _validate_non_empty(input.destination.account_holder_name, "destination.account_holder_name")
    _validate_non_empty(input.destination.account_number, "destination.account_number")

    normalized_customer = dataclasses.replace(input.customer, phone_number=normalized_phone)
    return dataclasses.replace(input, reference=reference, customer=normalized_customer)


def _apply_before_hook_mutation(mutated: Any, current: Any, prepare_fn: Any) -> Any:
    """Re-validate a ``before*`` hook's mutated output.

    Preserves the resolved reference when the hook omits one (keeps the
    original idempotency key), then re-runs the full validation suite so
    the hook cannot smuggle invalid values past the checks.
    """
    ref = mutated.reference if mutated.reference is not None else current.reference
    merged = dataclasses.replace(mutated, reference=ref)
    return prepare_fn(merged)


def _convert_status_result(result: Result[Any, str]) -> Result[StatusResponse, str]:
    """Convert a raw transport result into a StatusResponse dataclass."""
    if result.is_ok:
        return Ok(from_wire(StatusResponse, result.value))
    return Err(result.error)


def _convert_transaction_result(result: Result[Any, str]) -> Result[Transaction, str]:
    """Convert a raw transport result into a Transaction dataclass."""
    if result.is_ok:
        return Ok(from_wire(Transaction, result.value))
    return Err(result.error)


def _run_hook(hook: Any, *args: Any) -> Any:
    """Run a lifecycle hook safely.

    A disabled or unset hook is a no-op. The hook's ``fn`` runs inside a
    try/except so a throw in merchant code never bubbles into the payment
    flow — it is routed to ``on_error`` (which is itself wrapped, so a
    faulty handler can't crash us either).

    Returns the hook's resolved value, or ``None`` when skipped / failed.
    """
    if hook is None or not hook.enabled:
        return None

    result = Result.try_(lambda: hook.fn(*args))
    if result.is_err:
        Result.try_(lambda: hook.on_error(result.error))
        return None
    return result.value


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def create_sdk_instance(config: dict[str, Any]) -> NylonPaySdk:
    """Create an SDK instance with resolved configuration.

    Config dict keys: ``api_key``, ``api_secret``, ``base_url``, ``timeout_ms``,
    ``max_retries``, ``max_poll_interval_ms``, ``max_poll_duration_ms``,
    ``max_poll_attempts``, ``http_client``, ``hooks``.
    """
    transport = create_transport(
        {
            "api_key": config["api_key"],
            "api_secret": config["api_secret"],
            "base_url": config["base_url"],
            "timeout_ms": config["timeout_ms"],
            "max_retries": config["max_retries"],
            "http_client": config.get("http_client"),
        }
    )

    hooks: SdkHooks | None = config.get("hooks")

    common_deps: dict[str, Any] = {
        "fetch_status": lambda inp: _convert_status_result(
            transport["send"]({"action": SDK_ACTIONS["get_status"], "payload": to_wire(inp)})
        ),
        "fetch_transaction": lambda inp: _convert_transaction_result(
            transport["send"]({"action": SDK_ACTIONS["get_transaction"], "payload": to_wire(inp)})
        ),
        "poll_interval_ms": config.get("max_poll_interval_ms"),
        "max_poll_duration": config.get("max_poll_duration_ms"),
        "max_poll_attempts": config.get("max_poll_attempts"),
        "on_delayed": config.get("on_delayed", "wait"),
    }

    poll_deps: dict[str, Any] = {
        "fetch_status": common_deps["fetch_status"],
        "fetch_transaction": common_deps["fetch_transaction"],
        "poll_interval_ms": config.get("max_poll_interval_ms"),
        "max_poll_duration_ms": config.get("max_poll_duration_ms"),
        "max_poll_attempts": config.get("max_poll_attempts"),
        "on_delayed": config.get("on_delayed", "wait"),
    }

    def _continue_resolve_if_needed(
        transaction: Transaction,
    ) -> Result[Transaction, str]:
        if is_terminal_transaction_status(transaction.status):
            return Ok(transaction)
        return poll_until_terminal({**poll_deps, "reference": transaction.reference})

    def _hook_result(result: Result[Any, str]) -> Result[InitiationResult, str]:
        """Build the ``InitiationResult`` passed to after-hooks."""
        if result.is_ok:
            return Ok(
                InitiationResult(
                    reference=result.value["reference"],
                    status=result.value["status"],
                )
            )
        return Err(result.error)

    # ------------------------------------------------------------------
    # 1. collect_payment
    # ------------------------------------------------------------------

    def collect_payment(**kwargs: Any) -> PaymentInstance:
        """Initiate a collection. Returns a PaymentInstance with event emission."""
        input = coerce_dataclass(CollectPaymentInput, kwargs)
        payload = _prepare_collect_payload(input)
        mutated = _run_hook(hooks.before_collect if hooks else None, payload)
        if mutated is not None:
            payload = _apply_before_hook_mutation(mutated, payload, _prepare_collect_payload)

        result = transport["send"](
            {"action": SDK_ACTIONS["collect_payment"], "payload": to_wire(payload)}
        )

        _run_hook(
            hooks.after_collect if hooks else None,
            _hook_result(result),
            AfterHookInput(wire=payload, raw=input),
        )

        if result.is_err:
            sdk_err = parse_error(result.error)
            return create_payment_instance(
                {"reference": payload.reference, "status": "pending"},
                {**common_deps, "initial_error": sdk_err},
            )

        return create_payment_instance(result.value, common_deps)

    # ------------------------------------------------------------------
    # 2. collect_payment_and_resolve
    # ------------------------------------------------------------------

    def collect_payment_and_resolve(
        **kwargs: Any,
    ) -> Result[Transaction, str]:
        """Initiate a collection and block until terminal state."""
        input = coerce_dataclass(CollectPaymentInput, kwargs)
        payload = _prepare_collect_payload(input)
        mutated = _run_hook(hooks.before_collect if hooks else None, payload)
        if mutated is not None:
            payload = _apply_before_hook_mutation(mutated, payload, _prepare_collect_payload)

        result = transport["send"](
            {
                "action": SDK_ACTIONS["collect_payment_and_resolve"],
                "payload": to_wire(payload),
            }
        )

        _run_hook(
            hooks.after_collect if hooks else None,
            _hook_result(result),
            AfterHookInput(wire=payload, raw=input),
        )

        if result.is_ok:
            return _continue_resolve_if_needed(from_wire(Transaction, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 3. make_payout
    # ------------------------------------------------------------------

    def make_payout(**kwargs: Any) -> PaymentInstance:
        """Initiate a disbursement. Returns a PaymentInstance with event emission."""
        input = coerce_dataclass(MakePayoutInput, kwargs)
        payload = _prepare_payout_payload(input)
        mutated = _run_hook(hooks.before_payout if hooks else None, payload)
        if mutated is not None:
            payload = _apply_before_hook_mutation(mutated, payload, _prepare_payout_payload)

        result = transport["send"](
            {"action": SDK_ACTIONS["make_payout"], "payload": to_wire(payload)}
        )

        _run_hook(
            hooks.after_payout if hooks else None,
            _hook_result(result),
            AfterHookInput(wire=payload, raw=input),
        )

        if result.is_err:
            sdk_err = parse_error(result.error)
            return create_payment_instance(
                {"reference": payload.reference, "status": "pending"},
                {**common_deps, "initial_error": sdk_err},
            )

        return create_payment_instance(result.value, common_deps)

    # ------------------------------------------------------------------
    # 4. make_payout_and_resolve
    # ------------------------------------------------------------------

    def make_payout_and_resolve(
        **kwargs: Any,
    ) -> Result[Transaction, str]:
        """Initiate a disbursement and block until terminal state."""
        input = coerce_dataclass(MakePayoutInput, kwargs)
        payload = _prepare_payout_payload(input)
        mutated = _run_hook(hooks.before_payout if hooks else None, payload)
        if mutated is not None:
            payload = _apply_before_hook_mutation(mutated, payload, _prepare_payout_payload)

        result = transport["send"](
            {
                "action": SDK_ACTIONS["make_payout_and_resolve"],
                "payload": to_wire(payload),
            }
        )

        _run_hook(
            hooks.after_payout if hooks else None,
            _hook_result(result),
            AfterHookInput(wire=payload, raw=input),
        )

        if result.is_ok:
            return _continue_resolve_if_needed(from_wire(Transaction, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 5. get_status
    # ------------------------------------------------------------------

    def get_status(**kwargs: Any) -> Result[StatusResponse, str]:
        """One-shot status check. Does not poll."""
        input = GetStatusInput(**kwargs)
        _validate_non_empty(input.reference, "reference")

        result = transport["send"]({"action": SDK_ACTIONS["get_status"], "payload": to_wire(input)})

        if result.is_ok:
            return Ok(from_wire(StatusResponse, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 6. get_transaction
    # ------------------------------------------------------------------

    def get_transaction(
        **kwargs: Any,
    ) -> Result[Transaction, str]:
        """Look up a full transaction record by id or reference."""
        input = GetTransactionInput(**kwargs)
        if not input.id and not input.reference:
            _throw_validation("id or reference is required")

        result = transport["send"](
            {"action": SDK_ACTIONS["get_transaction"], "payload": to_wire(input)}
        )

        if result.is_ok:
            return Ok(from_wire(Transaction, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 7. list_transactions
    # ------------------------------------------------------------------

    def list_transactions(**kwargs: Any) -> Result[ListTransactionsResponse, str]:
        """List transactions with optional filters. Returns a paginated result."""
        input = coerce_dataclass(ListTransactionsInput, kwargs)

        result = transport["send"](
            {"action": SDK_ACTIONS["list_transactions"], "payload": to_wire(input)}
        )

        if result.is_ok:
            data = result.value
            summaries = [
                from_wire(TransactionSummary, tx) for tx in (data.get("transactions") or [])
            ]
            return Ok(
                ListTransactionsResponse(
                    transactions=summaries,
                    count=int(data.get("count", 0)),
                    limit=int(data.get("limit", 20)),
                    offset=int(data.get("offset", 0)),
                    tags=list(data.get("tags") or []),
                )
            )
        return Err(result.error)

    # ------------------------------------------------------------------
    # 8. get_transactions_by_tag
    # ------------------------------------------------------------------

    def get_transactions_by_tag(tag: str, **kwargs: Any) -> Result[ListTransactionsResponse, str]:
        """Shorthand for filtering by a single tag."""
        if not tag or not tag.strip():
            _throw_validation("tag is required")
        return list_transactions(tags=[tag], **kwargs)

    # ------------------------------------------------------------------
    # 9. verify_phone
    # ------------------------------------------------------------------

    def verify_phone(
        **kwargs: Any,
    ) -> Result[PhoneVerification, str]:
        """Pre-validate a phone number with the payment provider."""
        input = VerifyPhoneInput(**kwargs)
        _validate_non_empty(input.phone_number, "phone_number")
        normalized_phone = normalize_phone(input.phone_number)
        _validate_phone_format(normalized_phone, "phone_number")

        normalized_input = dataclasses.replace(input, phone_number=normalized_phone)
        result = transport["send"](
            {"action": SDK_ACTIONS["verify_phone"], "payload": to_wire(normalized_input)}
        )

        if result.is_ok:
            return Ok(from_wire(PhoneVerification, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 10. create_invoice
    # ------------------------------------------------------------------

    def create_invoice(
        **kwargs: Any,
    ) -> Result[InvoiceResponse, str]:
        """Generate an invoice and send it to the customer by email."""
        input = coerce_dataclass(CreateInvoiceInput, kwargs)
        _validate_collection_amount(input.amount)
        _validate_non_empty(input.customer_email, "customer_email")

        if input.items is not None:
            if len(input.items) > 50:
                _throw_validation("items must not exceed 50")
            for item in input.items:
                if (
                    not isinstance(item.quantity, int)
                    or isinstance(item.quantity, bool)
                    or item.quantity <= 0
                ):
                    _throw_validation("item quantity must be a positive integer")
                if (
                    not isinstance(item.unit_price, int)
                    or isinstance(item.unit_price, bool)
                    or item.unit_price <= 0
                ):
                    _throw_validation("item unit_price must be a positive integer")

        result = transport["send"](
            {"action": SDK_ACTIONS["create_invoice"], "payload": to_wire(input)}
        )

        if result.is_ok:
            return Ok(from_wire(InvoiceResponse, result.value))
        return Err(result.error)

    # ------------------------------------------------------------------
    # 11. verify_webhook_signature
    # ------------------------------------------------------------------

    def verify_webhook(**kwargs: Any) -> bool:
        """Verify a webhook payload signature. Delegates to standalone utility."""
        input = VerifyWebhookInput(**kwargs)
        return _verify_webhook_sig(input)

    # ------------------------------------------------------------------
    # Bundle into NylonPaySdk protocol
    # ------------------------------------------------------------------

    return cast(
        "NylonPaySdk",
        SimpleNamespace(
            collect_payment=collect_payment,
            collect_payment_and_resolve=collect_payment_and_resolve,
            make_payout=make_payout,
            make_payout_and_resolve=make_payout_and_resolve,
            get_status=get_status,
            get_transaction=get_transaction,
            list_transactions=list_transactions,
            get_transactions_by_tag=get_transactions_by_tag,
            verify_phone=verify_phone,
            create_invoice=create_invoice,
            verify_webhook_signature=verify_webhook,
        ),
    )
