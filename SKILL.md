---
name: nylonpay-py
description: Use when integrating Nylon Pay into a server-side Python app — collecting payments, sending payouts, checking transaction status, verifying phone numbers, creating hosted invoices, or verifying webhook signatures via the nylonpay-py SDK.
---

# Nylon Pay Python SDK

Server-side SDK for Nylon Pay. Python 3.10+. Published as `nylonpay-py`
(`pip install nylonpay-py`). Import package name: `nylonpay`.

## Setup

```bash
pip install nylonpay-py
```

```python
from nylonpay import create_nylon_pay

nylonpay = create_nylon_pay(
    api_key="npk_...",      # must start with "npk_"
    api_secret="nps_...",   # must start with "nps_"
)
```

- This is a **server-side** SDK. Never ship `api_secret` to a browser or mobile client.
- Test vs. live mode is decided by the **key**, not a config flag. A sandbox key
  routes to test providers; a live key moves real money. There is no `environment` option.
- Amounts are integers in the currency's smallest tracked unit (e.g. `10000`).
- Supported currencies: `USD`, `EUR`, `GBP`, `KES`, `UGX`, `TZS`, `RWF`.
- Nested inputs (`customer`, `destination`, `items`) accept plain dicts.

## Result type — read before writing any call

Sync operations return a `Result`. **Always branch on `is_ok` before touching `.value`.**

```python
from nylonpay import parse_error

result = nylonpay.get_status(reference="ORDER-2026-001")
if not result.is_ok:
    error = parse_error(result.error)  # structured: message, retryable, ...
    if error.retryable:
        pass  # safe to retry
    return
print(result.value.status)
```

## Choosing an operation

| Goal | Use | Shape |
|---|---|---|
| Take money, react to live updates | `collect_payment` | `PaymentInstance` (events) |
| Take money, await final state | `collect_payment_and_resolve` | `Result`, no client polling |
| Send money, react to live updates | `make_payout` | `PaymentInstance` |
| Send money, await final state | `make_payout_and_resolve` | `Result` |
| One-shot status | `get_status` | `Result` |
| Full transaction record | `get_transaction` | `Result` (`id` or `reference`) |
| Pre-validate phone / get name | `verify_phone` | `Result` |
| Hosted payment link (cards) | `create_invoice` | `Result` with `.url` |
| Authenticate webhook | `verify_webhook_signature` | `bool` |

**Prefer `*_and_resolve`** for simple request/response flows. Use event-driven
`PaymentInstance` only when you need progressive status updates.

## Event-driven flow

```python
payment = nylonpay.collect_payment(
    amount=10000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    description="Order #1234",
    method="mobileMoney",
    reference="ORDER-2026-001",  # optional; 13–15 chars if supplied
)

payment.on("success", lambda data: fulfill_order(data.transaction))
payment.on("failed", lambda data: notify_customer(data.error))
tx = payment.wait()
```

Events: `processing`, `success`, `failed`, `cancelled`, `error`.

## Webhooks

Verify on the **raw request body** before trusting any webhook:

```python
from nylonpay import verify_webhook_signature

is_valid = verify_webhook_signature(
    payload=raw_body,  # bytes/str, NOT re-serialized JSON
    signature=request.headers.get("x-nylon-signature"),
    secret=os.environ["NYLONPAY_WEBHOOK_SECRET"],
)
if not is_valid:
    return Response(status_code=401)
```

## Gotchas

- Use the raw, unparsed body for `verify_webhook_signature`.
- Card payments only via hosted `create_invoice`.
- Stable `reference` for idempotency: **13 to 15 characters** if you supply one
  (not a raw 36-character UUID).
- Field names are snake_case in Python (`phone_number`, `api_key`).
- Spec: [Nylon Pay SDK Spec](https://github.com/nile-squad/specs/blob/main/nylonpay-sdk-spec/spec.md).
