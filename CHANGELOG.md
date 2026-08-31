# Changelog

## 0.5.1

Upgrading from 0.5.0. **Upgrade if your metadata keys are not plain ASCII.**

### Fixed, critical

- **Requests with non-Latin metadata keys failed authentication.** The canonical
  payload sorted object keys by UTF-16 **little-endian** bytes, which is not
  UTF-16 code-unit order: little-endian compares the low byte first, so `"Ā"`
  (U+0100) sorted before `"Z"` (U+005A) where the correct order is the reverse.
  Any sibling key set containing a character whose low byte is below `0x20`, Cyrillic, CJK, Latin Extended, emoji, was canonicalized differently from the
  server, so a correctly-formed request was rejected as an authentication
  failure. Sorting is now by UTF-16 **big-endian** bytes, which is equivalent to
  code-unit order.

  Pure-ASCII payloads were never affected, so most integrations saw nothing. If
  you passed metadata keys such as `{"Ярлык": ...}` or `{"一括": ...}` alongside
  another key, those calls failed and now succeed.

### Added

- The spec's canonical signing conformance vectors V1–V7 now ship as a unit test
  (spec requirement S19). They are generated from the reference implementation
  and verified against the backend's verifier, so this SDK is now pinned to the
  backend rather than only to itself. V7 covers the ordering bug above.

## 0.5.0

Upgrading from 0.4.0, the previously published release.

### Fixed, critical

- **Webhook verification failed for every genuine webhook on Python 3.10.**
  Nylon Pay stamps deliveries with an ISO 8601 timestamp ending in `Z`.
  `datetime.fromisoformat` only accepts that suffix from Python 3.11 onward, so
  on 3.10 the freshness check could not read the timestamp and fell through to
  its fail-closed branch, `verify_webhook_signature` returned `False` for
  authentic webhooks. If you are on Python 3.10 and worked around this with
  `tolerance_seconds=0`, you can now remove that workaround and get replay
  protection back.

### Security

- **Signed responses are now bound to the request that asked for them.** The
  backend echoes the request's nonce inside the signed payload and the SDK
  requires it to match. Previously any response the backend had ever produced
  stayed validly signed forever and could be replayed onto a later call for the
  same reference. **Requires a backend that echoes the nonce; it is deployed
  first.**
- **`tolerance_seconds=0` no longer disables webhook replay protection.** It now
  means a tolerance of zero seconds, maximum strictness. Reaching for `0` to
  mean "strictest" previously turned the freshness check off entirely, silently.
  Pass `DISABLE_FRESHNESS_CHECK` to opt out deliberately.
- **The response body size cap is enforced while reading.** The transport now
  streams the response and aborts once the cap is exceeded; the old check read
  `Content-Length` after httpx had already buffered the whole body, so it never
  bounded peak memory and did nothing at all for a chunked response.
- **`reference` validation now uses whole-string matching.** Python's `$` also
  matches before a trailing newline, so `"<uuid>\n"` was accepted here while the
  TypeScript SDK rejected it, the reference is a cross-language contract and an
  idempotency key.

### Breaking

- **`InvoiceItem.amount` renamed to `unit_price`** (`unitPrice` on the wire).
  The backend has always required it under that name; the SDK dataclass and the
  spec both said `amount`, so `create_invoice` with line items failed
  validation for every merchant who followed the documented shape. Rename the
  field in your item objects, the value is unchanged (price per unit, smallest
  currency unit).
- **`tolerance_seconds=0` flips meaning** (see Security above).
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
