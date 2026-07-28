# Changelog

## 0.5.0

Upgrading from 0.4.0, the previously published release.

### Fixed — critical

- **Webhook verification failed for every genuine webhook on Python 3.10.**
  Nylon Pay stamps deliveries with an ISO 8601 timestamp ending in `Z`.
  `datetime.fromisoformat` only accepts that suffix from Python 3.11 onward, so
  on 3.10 the freshness check could not read the timestamp and fell through to
  its fail-closed branch — `verify_webhook_signature` returned `False` for
  authentic webhooks. If you are on Python 3.10 and worked around this with
  `tolerance_seconds=0`, you can now remove that workaround and get replay
  protection back.

### Breaking

- **`WebhookTransactionSnapshot` field types now match what the backend
  actually sends.** `amount` and `currency` are `str | None`; `type`, `method`,
  and `mode` are `T | None`. These fields could always arrive null.
  `transactionId` and `status` are always present, so use them to reconcile with
  `get_status`.
- **`WebhookTransactionSnapshot.statusText` removed.** The webhook payload never
  carried it. It remains on the `Transaction` shape, where it is genuinely sent.
- **Signature casing is unchanged but now deliberate.** Signatures have one form
  on the wire: lowercase hex, and any other spelling is rejected. This was
  already the behavior; it is now a stated guarantee shared with the TypeScript
  SDK rather than an accident of string comparison.

### Notes

- The standalone `verify_webhook_signature` takes a single `VerifyWebhookInput`.
  The client method `nylonpay.verify_webhook_signature(...)` is the
  keyword-argument form of the same check. Earlier documentation showed keyword
  arguments on the standalone function, which raises `TypeError`.
