# nylonpay-py

Server-side SDK for integrating Nylon Pay payment operations into your Python application.

[Full documentation](https://docs.nylonpay.nilesquad.com/docs)

## Install

```bash
pip install nylonpay-py
```

Requires Python 3.10+.

## Quick Start

Create a client, initiate a payment, subscribe to events, and wait for completion.

```python
from nylonpay import create_nylon_pay
import secrets

nylonpay = create_nylon_pay(
    api_key="npk_test_...",
    api_secret="nps_test_...",
)

payment = nylonpay.collect_payment(
    amount=10000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    description="Order #1234",
    reference=secrets.token_hex(7),
)

def on_success(data):
    print(f"Paid: {data.transaction.reference}")

def on_failed(data):
    print(f"Failed: {data.error}")

payment.on("success", on_success)
payment.on("failed", on_failed)

tx = payment.wait()
if tx is not None:
    print(f"Transaction {tx.reference} completed")
```

## Configuration

Create the SDK instance with `create_nylon_pay()`. All options are keyword arguments.

Your API key determines the mode — `npk_sandbox_...` for test mode, `npk_live_...` for production. There is no separate `mode` option.

| Field | Required | Default | Description |
|---|---|---|---|
| `api_key` | Yes | | Must start with `npk_` |
| `api_secret` | Yes | | Must start with `nps_` |
| `base_url` | No | `https://api.nylonpay.nilesquad.com/api/services` | Override for a custom endpoint |
| `timeout_ms` | No | `30000` | Request timeout in milliseconds |
| `max_retries` | No | `3` | Retry count for failed requests |
| `max_poll_interval_ms` | No | `2000` | Interval between status checks |
| `max_poll_duration_ms` | No | *(none)* | Optional cap on total wait time. Omit to wait until terminal. |
| `max_poll_attempts` | No | *(none)* | Optional cap on status checks. Omit to wait until terminal. |
| `on_delayed` | No | `"wait"` | `"return"` hands back a delayed still-pending payment; `"wait"` keeps polling |
| `force` | No | `False` | Bypass instance cache and create a fresh instance |
| `hooks` | No | `None` | Lifecycle hooks (`SdkHooks`) for cross-cutting concerns |
| `http_client` | No | `None` | `httpx.Client` for testing injection |

```python
nylonpay = create_nylon_pay(
    api_key="npk_test_...",
    api_secret="nps_test_...",
    timeout_ms=15000,
    max_retries=5,
)
```

The factory caches instances by `api_key + base_url + sha256(api_secret)`. Rotating the secret produces a different cache key and a fresh instance. Pass `force=True` to bypass caching.

## Operations

All operations accept keyword arguments. Nested types (`customer`, `destination`, `items`) accept plain dicts — no need to import dataclasses.

### collect_payment

Initiate a payment collection. Returns a `PaymentInstance` with event-driven updates.

```python
payment = nylonpay.collect_payment(
    amount=10000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    description="Order #1234",
    method="mobileMoney",
    reference="ORDER-2026-001",
)

def on_success(data):
    print(f"Paid: {data.transaction.reference}")

def on_failed(data):
    print(f"Failed: {data.error}")

payment.on("success", on_success)
payment.on("failed", on_failed)
```

`reference` is optional and auto-generated if omitted. A supplied reference must be **13 to 15 characters**; the SDK raises `SdkException` with category `validation` otherwise. A raw UUID is 36 characters and will be rejected — use a short id of your own or omit the field.

### collect_payment_and_resolve

Block until the collection reaches a terminal state. Single request/response — the server checks status internally, no client-side waiting.

```python
result = nylonpay.collect_payment_and_resolve(
    amount=5000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    description="Quick payment",
)

if result.is_ok:
    print("Paid:", result.value.reference)
```

### make_payout

Disburse funds to a destination account. Returns a `PaymentInstance` with event-driven updates.

```python
payout = nylonpay.make_payout(
    amount=50000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    destination={
        "account_holder_name": "Jane Doe",
        "account_number": "123456",
    },
    description="Refund for order #1234",
)

tx = payout.wait()
```

### make_payout_and_resolve

Block until the payout reaches a terminal state. Single request/response.

```python
result = nylonpay.make_payout_and_resolve(
    amount=50000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    destination={
        "account_holder_name": "Jane Doe",
        "account_number": "123456",
    },
    description="Refund",
)

if result.is_ok:
    print("Payout completed:", result.value.reference)
```

### get_status

One-shot status check for a transaction. Does not wait — returns the current server-side state.

```python
result = nylonpay.get_status(reference="ORDER-2026-001")
if result.is_ok:
    print(result.value.status)
```

### get_transaction

Look up a full transaction record by `id` or `reference`. At least one must be provided.

```python
result = nylonpay.get_transaction(reference="ORDER-2026-001")
if result.is_ok:
    print(result.value.failure_reason)
```

### verify_phone

Pre-validate a phone number and get the registered name.

```python
result = nylonpay.verify_phone(phone_number="+256700000000")
if result.is_ok and result.value.verified:
    print("Registered to:", result.value.customer_name)
```

Phone numbers are normalized automatically — any common format works: `+256 700 000 000`, `0700000000`, `256700000000` are all accepted.

### create_invoice

Generate a hosted payment link. Card payments are only supported via this hosted flow — card details never reach your servers.

```python
result = nylonpay.create_invoice(
    amount=25000,
    currency="UGX",
    description="Monthly subscription",
    items=[{"name": "Pro Plan", "quantity": 1, "unit_price": 25000}],
    redirect_url="https://myapp.com/thank-you",
)

if result.is_ok:
    print("Invoice URL:", result.value.url)
```

### verify_webhook_signature

Verify incoming webhook payloads before processing. Operates on raw payload bytes or string — never re-serialize parsed JSON, which would alter the signed content.

```python
from nylonpay import verify_webhook_signature

is_valid = verify_webhook_signature(
    payload=raw_payload_bytes,
    signature=signature_header,
    secret="nps_...",
)

if not is_valid:
    # Reject — payload did not originate from Nylon Pay
    ...
```

The verification checks authenticity and freshness. Pass `tolerance_seconds=0` to disable the freshness check. Returns `True` only when both checks pass. Never raises.

## PaymentInstance Events

`collect_payment` and `make_payout` return a `PaymentInstance` with event-driven updates.

| Event | Description |
|---|---|
| `processing` | Transaction is being processed |
| `success` | Transaction completed successfully |
| `failed` | Transaction failed |
| `cancelled` | Transaction was cancelled |
| `error` | Network or server error |

```python
def on_success(data):
    print(f"Paid: {data.transaction.reference}")

payment.on("success", on_success)
payment.once("success", on_success)  # fires at most once
payment.off("success", on_success)   # remove handler

tx = payment.wait()
```

### wait()

Block until terminal state. Returns `Transaction` on success, `None` on failure, cancellation, or error. Never raises. **Default:** waits until the payment finishes with no built-in time limit.

```python
tx = payment.wait()
if tx is not None:
    print("paid:", tx.reference)
else:
    print("failed or timed out")
```

**Delayed payments (v0.4+):** After about three minutes in flight, responses may include `delayed=True`. Use `on_delayed="return"` to get the still-pending payment back and rely on webhooks:

```python
nylonpay = create_nylon_pay(
    api_key="npk_test_...",
    api_secret="nps_test_...",
    on_delayed="return",
)

result = nylonpay.collect_payment_and_resolve(...)
if result.is_ok and result.value.delayed and result.value.status == "pending":
    # Still in flight — handle via webhooks
    ...
```

Set `max_poll_duration_ms` to restore a bounded wait (~5 minutes previously).

## Error Handling

Operations that return `Result[T, str]` use the SDK's `Result` type. Check `.is_ok` / `.is_err` before accessing `.value` / `.error`.

```python
from nylonpay import parse_error

result = nylonpay.get_status(reference="ORDER-2026-001")
if result.is_err:
    error = parse_error(result.error)
    if error.retryable:
        # Retry the operation
        ...
    print(f"Category: {error.category}, Message: {error.message}")
```

### SdkException

Operations that throw on initiation failure (invalid input, missing fields) raise `SdkException`. It carries structured error information.

```python
from nylonpay import SdkException

try:
    payment = nylonpay.collect_payment(
        amount=100,
        currency="UGX",
        customer={"name": "Jane", "phone_number": "+256700000000"},
        description="Test",
    )
except SdkException as e:
    print(f"Category: {e.category}")
    print(f"Retryable: {e.retryable}")
    print(f"Message: {e}")
```

### Error Categories

| Category | Description | Retryable |
|---|---|---|
| `auth` | Invalid credentials | No |
| `validation` | Invalid input | No |
| `limit` | Account limit exceeded | No |
| `rate_limit` | Rate limited | Yes |
| `account` | Account issue (suspended, etc.) | No |
| `provider` | Provider rejected the transaction | No |
| `duplicate` | Reference already used | No |
| `not_found` | Resource not found | No |
| `internal` | Server error | Varies |
| `network` | Network error | Yes |
| `timeout` | Request timed out | Yes |

## Hooks

Lifecycle hooks fire on every matching operation. Use them for cross-cutting concerns like logging, audit trails, and payload enrichment.

Each hook is wrapped in `SdkHook` which provides a safe boundary — if the hook's `fn` raises an exception, it is routed to `on_error` instead of crashing the payment flow.

```python
from nylonpay import create_nylon_pay, SdkHook, SdkHooks

def log_before_collect(input):
    print(f"About to collect: {input.reference}")
    return input  # can mutate and return, or return None to skip

def log_after_collect(result, after_input):
    if result.is_ok:
        print(f"Collected: {result.value.reference}")
    else:
        print(f"Failed: {result.error}")

def on_hook_error(exc):
    print(f"Hook failed: {exc}")

hooks = SdkHooks(
    before_collect=SdkHook(fn=log_before_collect, on_error=on_hook_error),
    after_collect=SdkHook(fn=log_after_collect, on_error=on_hook_error),
)

nylonpay = create_nylon_pay(
    api_key="npk_test_...",
    api_secret="nps_test_...",
    hooks=hooks,
)
```

Available hooks: `before_collect`, `after_collect`, `before_payout`, `after_payout`. Each can be `None` (no-op).

## Supported Currencies

`USD`, `EUR`, `GBP`, `KES`, `UGX`, `TZS`, `RWF`

## Links

- [Documentation](https://docs.nylonpay.nilesquad.com/docs)
- [SDK Spec](https://github.com/nile-squad/specs/blob/main/nylonpay-sdk-spec/spec.md)
- [GitHub Repository](https://github.com/nile-squad/nylonpay-py)
- [TypeScript SDK](https://github.com/nile-squad/nylonpay-ts)
- [Nylon Pay](https://nylonpay.nilesquad.com)

## License

MIT
