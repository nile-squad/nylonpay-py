"""Nylon Pay SDK for merchant integrations.

Server-side SDK for collecting payments, making payouts, verifying phones,
creating invoices, checking transaction status, and verifying webhooks.

Example:
    from nylonpay import create_nylon_pay

    nylonpay = create_nylon_pay(
        api_key="npk_live_...",
        api_secret="nps_live_...",
    )

    payment = nylonpay.collect_payment(
        amount=10000,
        currency="UGX",
        customer={"name": "Jane", "phone_number": "+256700000000"},
        description="Order #1234",
    )
    payment.on("success", lambda data: print("Paid:", data.transaction))
"""

from .factory import create_nylon_pay
from .slang import Err, Ok, Result
from .transport import SdkException, create_sdk_error, parse_error
from .types import (
    AfterCollectHook,
    AfterHookInput,
    AfterPayoutHook,
    BankDetails,
    BeforeCollectHook,
    BeforePayoutHook,
    CollectPaymentInput,
    CreateInvoiceInput,
    Currency,
    Customer,
    Destination,
    EventData,
    GetStatusInput,
    GetTransactionInput,
    InitiationResult,
    InvoiceItem,
    InvoiceResponse,
    MakePayoutInput,
    NylonPayConfig,
    NylonPaySdk,
    PaymentEvent,
    PaymentEventHandler,
    PaymentInstance,
    PaymentMethod,
    PhoneVerification,
    SdkError,
    SdkErrorCategory,
    SdkHook,
    SdkHooks,
    StatusResponse,
    Transaction,
    TransactionMode,
    TransactionStatus,
    TransactionType,
    VerifyPhoneInput,
    VerifyWebhookInput,
    WebhookEventType,
    WebhookPayload,
    WebhookTransactionSnapshot,
)
from .verify_webhook import DISABLE_FRESHNESS_CHECK, verify_webhook_signature

__all__ = [
    "DISABLE_FRESHNESS_CHECK",
    # Types
    "AfterCollectHook",
    "AfterHookInput",
    "AfterPayoutHook",
    "BankDetails",
    "BeforeCollectHook",
    "BeforePayoutHook",
    "CollectPaymentInput",
    "CreateInvoiceInput",
    "Currency",
    "Customer",
    "Destination",
    "Err",
    "EventData",
    "GetStatusInput",
    "GetTransactionInput",
    "InitiationResult",
    "InvoiceItem",
    "InvoiceResponse",
    "MakePayoutInput",
    "NylonPayConfig",
    "NylonPaySdk",
    "Ok",
    "PaymentEvent",
    "PaymentEventHandler",
    "PaymentInstance",
    "PaymentMethod",
    "PhoneVerification",
    "Result",
    "SdkError",
    "SdkErrorCategory",
    "SdkException",
    "SdkHook",
    "SdkHooks",
    "StatusResponse",
    "Transaction",
    "TransactionMode",
    "TransactionStatus",
    "TransactionType",
    "VerifyPhoneInput",
    "VerifyWebhookInput",
    "WebhookEventType",
    "WebhookPayload",
    "WebhookTransactionSnapshot",
    "create_nylon_pay",
    "create_sdk_error",
    "parse_error",
    "verify_webhook_signature",
]
