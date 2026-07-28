"""All public type definitions for the Nylon Pay SDK.

Every type in this module is part of the public API. Field names use
snake_case (Python convention); the transport layer converts to camelCase
for the wire payload. Type names use PascalCase, constants use UPPER_SNAKE.

These types are the contract between merchant code and the SDK. They're
frozen dataclasses (immutable after construction) so merchants can safely
pass them around without worrying about accidental mutation mid-operation.
The shapes, field names (after casing conversion), and value constraints
match the SDK spec (v1.3.0) — every SDK implementation exposes the same
fields so backend behavior is predictable regardless of language.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    TypeVar,
    runtime_checkable,
)

import httpx

from .slang import Result

# --- Literal type aliases ---

TransactionStatus = Literal[
    "pending",
    "processing",
    "on_hold",
    "successful",
    "failed",
    "cancelled",
]

TransactionType = Literal[
    "collection",
    "payout",
    "transfer",
    "escrow",
    "refund",
    "reversal",
    "charge",
    "chargeback",
]

PaymentMethod = Literal["mobileMoney", "bank"]

TransactionMode = Literal["test", "live"]

PaymentEvent = Literal["processing", "success", "failed", "cancelled", "error"]

WebhookEventType = Literal[
    "transaction.successful",
    "transaction.failed",
    "transaction.processing",
    "transaction.cancelled",
]

Currency = Literal["USD", "EUR", "GBP", "KES", "UGX", "TZS", "RWF"]

SdkErrorCategory = Literal[
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
]


# --- Input dataclasses ---


@dataclass(frozen=True)
class Customer:
    """Customer details attached to a payment.

    The phone number is the primary identity for mobile-money collections;
    email is optional and used for receipts when available.
    """

    name: str
    phone_number: str
    email: str | None = None


@dataclass(frozen=True)
class Destination:
    """Destination account for a payout.

    The account holder name must match KYC records to reduce reversal risk.
    """

    account_holder_name: str
    account_number: str
    bank_name: str | None = None
    phone: str | None = None


@dataclass(frozen=True)
class InvoiceItem:
    """Line item for an invoice.

    Merchants use these to render itemized breakdowns on the hosted payment page.
    """

    name: str
    quantity: int
    #: Price per unit in the smallest currency unit (e.g. UGX shillings).
    #: Serialized to the wire as ``unitPrice``.
    unit_price: int


@dataclass(frozen=True)
class BankDetails:
    """Bank account details required when the payment method is ``"bank"``."""

    account_number: str
    bank_name: str


@dataclass(frozen=True)
class CollectPaymentInput:
    """Input for initiating a collection.

    The SDK abstracts provider routing, so the merchant only specifies
    what to collect, from whom, and how.
    """

    amount: int
    currency: Currency
    customer: Customer
    description: str
    reference: str | None = None
    method: PaymentMethod | None = None
    bank: BankDetails | None = None
    tags: list[str] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MakePayoutInput:
    """Input for initiating a payout.

    Use this to disburse funds to a customer's bank account or
    mobile-money wallet.
    """

    amount: int
    currency: Currency
    customer: Customer
    destination: Destination
    description: str
    reference: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GetStatusInput:
    """Input for a one-shot status check.

    Does not start polling; returns the current server-side state.
    """

    reference: str


@dataclass(frozen=True)
class GetTransactionInput:
    """Input for looking up a full transaction record.

    At least one of ``id`` or ``reference`` must be provided.
    """

    id: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class VerifyPhoneInput:
    """Input for phone-number pre-validation.

    Returns the registered name on the account so merchants can confirm
    customer identity before initiating a collection or payout.
    """

    phone_number: str
    purpose: Literal["collection", "payout"] | None = None


@dataclass(frozen=True)
class CreateInvoiceInput:
    """Input for creating an invoice.

    An invoice email is sent to the customer automatically. The returned
    payment link directs the customer to a mobile-money payment page.
    """

    amount: int
    currency: Currency
    customer_email: str
    customer_name: str | None = None
    customer_phone: str | None = None
    description: str | None = None
    due_date: str | None = None
    items: list[InvoiceItem] | None = None
    merchant_reference: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ListTransactionsInput:
    """Filters for listing transactions.

    All fields are optional — omit to return all transactions for the account.
    Multiple tags use AND semantics: only transactions carrying every listed
    tag are returned.
    """

    tags: list[str] | None = None
    status: TransactionStatus | None = None
    type: TransactionType | None = None
    limit: int | None = None
    offset: int | None = None
    created_after: str | None = None
    created_before: str | None = None


@dataclass(frozen=True)
class VerifyWebhookInput:
    """Input for verifying a webhook signature.

    Operates on raw payload bytes to avoid re-serialization altering
    the signed content.
    """

    payload: str | bytes
    signature: str
    secret: str
    tolerance_seconds: int | None = None


# --- Response dataclasses ---


@dataclass(frozen=True)
class TransactionSummary:
    """Lightweight transaction record returned by list operations.

    Contains the fields needed for filtering, display, and reconciliation
    without the full provider-level detail of :class:`Transaction`.
    """

    id: str
    reference: str
    amount: int
    currency: Currency
    status: TransactionStatus
    type: TransactionType
    mode: TransactionMode
    tags: list[str]
    created_at: str
    updated_at: str
    method: str | None = None


@dataclass(frozen=True)
class ListTransactionsResponse:
    """Response from :meth:`NylonPaySdk.list_transactions`."""

    transactions: list[TransactionSummary]
    count: int
    limit: int
    offset: int
    tags: list[str]


@dataclass(frozen=True)
class Transaction:
    """Full transaction record returned by lookups, event handlers, and
    the blocking resolve variants.

    Contains everything a merchant needs to reconcile without leaking
    internal provider details.
    """

    id: str
    reference: str
    amount: int
    currency: Currency
    status: TransactionStatus
    type: TransactionType
    method: PaymentMethod
    description: str
    phone: str
    email: str | None
    failure_reason: str | None
    metadata: dict[str, str]
    mode: TransactionMode
    created_at: str
    updated_at: str
    duplicate: bool | None = None
    operator_tid: str | None = None
    status_text: str | None = None
    delayed: bool | None = None


@dataclass(frozen=True)
class StatusResponse:
    """Lightweight status response for quick checks.

    Use when you only need the current state, not the full transaction record.
    """

    reference: str
    status: TransactionStatus
    amount: int
    currency: Currency
    updated_at: str
    status_text: str | None = None
    delayed: bool | None = None


@dataclass(frozen=True)
class PhoneVerification:
    """Result of a phone verification call.

    ``verified`` is True when the provider confirms the number is active
    and the returned name matches expectations.
    """

    phone_number: str
    customer_name: str
    verified: bool


@dataclass(frozen=True)
class InvoiceResponse:
    """Response from creating an invoice."""

    id: str
    invoice_number: str
    payment_link: str
    amount: str
    currency: str
    status: str


@dataclass(frozen=True)
class WebhookTransactionSnapshot:
    """Merchant-facing transaction record delivered inside a webhook payload.

    Field names match the webhook JSON body exactly; this type is not passed
    through wire-case conversion. Merchants can construct it directly from
    ``json.loads(req.body)`` output for full type confidence on the
    ``payload`` field of :class:`WebhookPayload`.
    """

    transactionId: str
    reference: str
    # ``None`` in the rare case where the backend could not read the
    # transaction record while dispatching. ``transactionId`` and ``status``
    # are always present, so reconcile with ``get_status`` if you see one.
    amount: str | None
    currency: str | None
    status: TransactionStatus
    previousStatus: TransactionStatus
    # These three are ``None`` whenever the backend has no value stored for
    # the transaction (older rows especially) — it sends the key with an
    # explicit null rather than omitting it.
    type: TransactionType | None
    method: PaymentMethod | None
    mode: TransactionMode | None
    failureReason: str | None
    operatorTid: str | None


@dataclass(frozen=True)
class WebhookPayload:
    """Structured payload delivered to the merchant's webhook endpoint.

    Merchants should verify the ``x-nylon-signature`` header before
    trusting the data — the signature does NOT live in the body.
    """

    delivery_id: str
    event: WebhookEventType
    payload: WebhookTransactionSnapshot
    timestamp: str


# --- Error types ---


@dataclass(frozen=True)
class SdkError:
    """Structured error returned by SDK operations.

    ``category`` is machine-readable for branching logic; ``message`` is
    human-readable for logs and alerts. ``retryable`` tells the merchant
    whether the same request may succeed on re-invocation.
    """

    category: SdkErrorCategory
    message: str
    retryable: bool | None = None


# --- Event types ---


@dataclass(frozen=True)
class EventData:
    """Data passed to every payment event handler.

    ``reference`` is always present; ``transaction`` is populated for
    terminal status events (``success``, ``failed``, ``cancelled``) —
    the ``processing`` event can fire before the full record is fetched,
    so use ``reference`` there. ``error`` is populated for the ``"error"``
    event (network failure, timeout, reference mismatch).
    """

    event: PaymentEvent
    reference: str
    timestamp: str
    transaction: Transaction | None = None
    error: str | None = None
    category: SdkErrorCategory | None = None
    retryable: bool | None = None


PaymentEventHandler = Callable[[EventData], None]


# --- Hook types ---


@dataclass(frozen=True)
class InitiationResult:
    """Result of a payment initiation — reference and initial status.

    Used as the success value in the Result passed to after-hooks.
    """

    reference: str
    status: str


TInput = TypeVar("TInput")


@dataclass(frozen=True)
class AfterHookInput(Generic[TInput]):
    """The input handed to an ``after*`` hook.

    Contains the final wire payload (reference resolved, phone normalized,
    ``before*``-hook mutations applied) as ``wire``, plus ``raw`` carrying
    the untouched original merchant input. This lets a hook log both what
    hit the wire and what the merchant typed.
    """

    wire: TInput
    raw: TInput


BeforeCollectHook = Callable[[CollectPaymentInput], "CollectPaymentInput | None"]

AfterCollectHook = Callable[
    [Result[InitiationResult, str], AfterHookInput[CollectPaymentInput]],
    None,
]

BeforePayoutHook = Callable[[MakePayoutInput], "MakePayoutInput | None"]

AfterPayoutHook = Callable[
    [Result[InitiationResult, str], AfterHookInput[MakePayoutInput]],
    None,
]

HookFn = TypeVar("HookFn")


@dataclass(frozen=True)
class SdkHook(Generic[HookFn]):
    """Wrapper applied to every lifecycle hook.

    The SDK runs ``fn`` inside a safe boundary, so a throw or exception in
    merchant code never bubbles into the payment flow — it is routed to
    ``on_error`` instead.

    WHY ``on_error`` is required: an unhandled hook failure in a payments
    SDK is the worst kind of silent bug (the payment "succeeds" while a
    wallet credit or fulfillment side-effect was lost). Forcing the
    merchant to declare what happens on failure replaces both the old
    "throw and maybe crash" behaviour and a silent ``except: pass`` with
    an explicit, type-enforced decision.
    """

    fn: HookFn
    on_error: Callable[[BaseException], None]
    enabled: bool = True


@dataclass(frozen=True)
class SdkHooks:
    """Lifecycle hooks registered once at SDK creation.

    Each hook fires on every matching operation — use them for
    cross-cutting concerns like logging, audit trails, and payload
    enrichment. Every hook is wrapped in :class:`SdkHook` so merchant
    code can never crash the payment flow.
    """

    before_collect: SdkHook[BeforeCollectHook] | None = None
    after_collect: SdkHook[AfterCollectHook] | None = None
    before_payout: SdkHook[BeforePayoutHook] | None = None
    after_payout: SdkHook[AfterPayoutHook] | None = None


# --- Config ---


@dataclass(frozen=True)
class NylonPayConfig:
    """SDK configuration supplied by the merchant at initialization.

    All timeouts and retry limits are configurable for different
    network environments.

    Test vs. live mode is determined by the API key, not by config —
    a sandbox key routes to test providers, a live key processes
    real money.
    """

    api_key: str
    api_secret: str
    base_url: str | None = None
    timeout_ms: int | None = None
    max_retries: int | None = None
    max_poll_interval_ms: int | None = None
    max_poll_duration_ms: int | None = None
    max_poll_attempts: int | None = None
    on_delayed: str | None = None
    force: bool = False
    hooks: SdkHooks | None = None
    http_client: httpx.Client | None = None


# --- Protocol contracts ---


@runtime_checkable
class PaymentInstance(Protocol):
    """Event-driven handle for a payment operation.

    Subscribe to status transitions with ``on``/``once``/``off``, or
    block until completion with ``wait``.

    Implemented as a ``SimpleNamespace`` with closures — no class.
    ``reference`` and ``status`` are plain attributes (``reference`` is
    immutable after creation, ``status`` is updated in place by the
    polling loop).
    """

    reference: str
    status: TransactionStatus

    def on(self, event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        """Register a handler for a payment event. Returns the instance for chaining."""
        ...

    def once(self, event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        """Register a handler that fires at most once, then auto-unsubscribes."""
        ...

    def off(self, event: PaymentEvent, handler: PaymentEventHandler) -> PaymentInstance:
        """Remove a previously registered handler. Safe to call for unregistered handlers."""
        ...

    def wait(self) -> Transaction | None:
        """Block until terminal state. Returns the full Transaction on
        success, or ``None`` on failure, cancellation, or polling error.
        Never raises.
        """
        ...


@runtime_checkable
class NylonPaySdk(Protocol):
    """SDK instance returned by the factory.

    Provides all payment operations and the webhook verification utility.
    All operations are synchronous — no asyncio.
    """

    def collect_payment(self, **kwargs: Any) -> PaymentInstance:
        """Initiate a payment collection. Returns a PaymentInstance that polls
        for status updates and emits events. Throws synchronously only on
        invalid input — server-side initiation rejections surface as an
        ``"error"`` event.
        """
        ...

    def collect_payment_and_resolve(self, **kwargs: Any) -> Result[Transaction, str]:
        """Initiate a collection and block until terminal state. Single
        request/response call — server polls internally.
        """
        ...

    def make_payout(self, **kwargs: Any) -> PaymentInstance:
        """Initiate a disbursement. Returns a PaymentInstance that polls
        for status updates and emits events.
        """
        ...

    def make_payout_and_resolve(self, **kwargs: Any) -> Result[Transaction, str]:
        """Initiate a disbursement and block until terminal state. Single
        request/response call.
        """
        ...

    def get_status(self, **kwargs: Any) -> Result[StatusResponse, str]:
        """One-shot status check. Does not poll — returns current server state."""
        ...

    def get_transaction(self, **kwargs: Any) -> Result[Transaction, str]:
        """Look up a full transaction record by id or reference."""
        ...

    def list_transactions(self, **kwargs: Any) -> Result[ListTransactionsResponse, str]:
        """List transactions for the account with optional filters.

        Multiple tags use AND semantics — only transactions carrying all
        listed tags are returned. Returns a paginated result.
        """
        ...

    def get_transactions_by_tag(
        self, tag: str, **kwargs: Any
    ) -> Result[ListTransactionsResponse, str]:
        """Shorthand for filtering by a single tag.

        Equivalent to ``list_transactions(tags=[tag], **kwargs)``.
        """
        ...

    def verify_phone(self, **kwargs: Any) -> Result[PhoneVerification, str]:
        """Pre-validate a phone number with the payment provider."""
        ...

    def create_invoice(self, **kwargs: Any) -> Result[InvoiceResponse, str]:
        """Create an invoice and email it to the customer. The customer
        receives a PDF invoice and a payment link for mobile money payment.
        """
        ...

    def verify_webhook_signature(self, **kwargs: Any) -> bool:
        """Verify that an incoming webhook payload was signed by Nylon Pay.
        Operates on raw payload bytes to prevent re-serialization issues.
        """
        ...
