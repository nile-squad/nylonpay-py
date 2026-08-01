---
name: nylonpay-py
description: Use when integrating Nylon Pay into a server-side Python app, collecting payments, sending payouts, checking transaction status, verifying phone numbers, creating hosted invoices, or verifying webhook signatures via the nylonpay-py SDK.
---

# Nylon Pay Python SDK

Server-side SDK for Nylon Pay. Python 3.10+. Published as `nylonpay-py`
(`pip install nylonpay-py`). Import package name: `nylonpay`.

Same product surface as the [TypeScript](https://docs.nylonpay.nilesquad.com/docs/skills/typescript)
and [PHP](https://docs.nylonpay.nilesquad.com/docs/skills/php) SDKs. Names here are
snake_case. Hub: [nylonpay-overview](https://github.com/nile-squad/nylonpay-overview).

## Setup

```bash
pip install nylonpay-py
```

```python
from nylonpay import create_nylon_pay, parse_error

nylonpay = create_nylon_pay(
    api_key="npk_...",  # must start with "npk_"
    api_secret="nps_...",  # must start with "nps_"
)
```

- Server-side only. Never ship `api_secret` to a browser or mobile client.
- Test vs live mode comes from the **key**, not a config flag. Use your sandbox
  key for test transactions and your live key for real money. There is no
  `environment` option.
- Amounts are integers in the currency's smallest tracked unit (for example `10000`).
- Supported currencies: `USD`, `EUR`, `GBP`, `KES`, `UGX`, `TZS`, `RWF`.
- Nested inputs (`customer`, `destination`, `items`) accept plain dicts.

## Result type, read before writing any call

Sync operations return a `Result`. **Always branch on `is_ok` before touching `.value`.**

```python
result = nylonpay.get_status(reference="550e8400-e29b-41d4-a716-446655440000")
if not result.is_ok:
    error = parse_error(result.error)  # message, retryable, category, ...
    if error.retryable:
        pass  # safe to retry
    return
print(result.value.status)
```

## Choosing an operation

| Goal | Use | Shape |
|---|---|---|
| Take money, react to live updates | `collect_payment` | `PaymentInstance` (events) |
| Take money, await final state | `collect_payment_and_resolve` | `Result` |
| Send money, react to live updates | `make_payout` | `PaymentInstance` |
| Send money, await final state | `make_payout_and_resolve` | `Result` |
| One-shot status | `get_status` | `Result` |
| Full transaction record | `get_transaction` | `Result` (`id` or `reference`) |
| Pre-validate phone / get name | `verify_phone` | `Result` |
| Hosted payment link (cards) | `create_invoice` | `Result` with `.payment_link` |
| Authenticate webhook | `verify_webhook_signature` | `bool` |

Prefer `*_and_resolve` for simple request/response flows. Use event-driven
`PaymentInstance` when you need progressive status updates.

## Event-driven flow

```python
payment = nylonpay.collect_payment(
    amount=10000,
    currency="UGX",
    customer={"name": "Jane", "phone_number": "+256700000000"},
    description="Order #1234",
    method="mobileMoney",
    # optional; omit to auto-generate a UUID v4
    reference="550e8400-e29b-41d4-a716-446655440000",
)

payment.on("success", lambda data: fulfill_order(data.transaction))
payment.on("failed", lambda data: notify_customer(data.error))
tx = payment.wait()  # transaction or None, does not raise on failure
```

Events: `processing`, `success`, `failed`, `cancelled`, `error`.

## Webhooks

Verify on the **raw request body** before trusting any webhook:

```python
import os
from nylonpay import verify_webhook_signature

is_valid = verify_webhook_signature(
    payload=raw_body,  # bytes/str, not re-serialized JSON
    signature=request.headers.get("x-nylon-signature"),
    secret=os.environ["NYLONPAY_WEBHOOK_SECRET"],
)
if not is_valid:
    return Response(status_code=401)
```

## Gotchas

- Use the raw, unparsed body for `verify_webhook_signature`.
- Card payments only via hosted `create_invoice` (read `.payment_link`).
- Idempotency: pass a stable UUID `reference` you own, or omit it for an
  auto-generated UUID v4. Non-UUID values raise a validation error.
- Field names are snake_case (`phone_number`, `api_key`, `payment_link`).
- Spec: [Nylon Pay SDK Spec](https://github.com/nile-squad/specs/blob/main/nylonpay-sdk-spec/spec.md).

## Other language SDKs

| Language | Package | Agent skill |
|---|---|---|
| TypeScript | [`@nile-squad/nylonpay-ts`](https://github.com/nile-squad/nylonpay-ts) | [docs](https://docs.nylonpay.nilesquad.com/docs/skills/typescript) |
| PHP | [`nile-squad/nylonpay-php`](https://github.com/nile-squad/nylonpay-php) | [docs](https://docs.nylonpay.nilesquad.com/docs/skills/php) |

Public hub: [nylonpay-overview](https://github.com/nile-squad/nylonpay-overview).
Example prompts: [docs](https://docs.nylonpay.nilesquad.com/docs/skills/example-prompts).
