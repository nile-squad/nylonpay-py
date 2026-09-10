"""Parse recorded backend fixtures so InvoiceResponse cannot drift again."""

from __future__ import annotations

import json
from pathlib import Path

from nylonpay.types import InvoiceResponse, Transaction, WebhookTransactionSnapshot
from nylonpay.wire import from_wire

FIXTURES = (
    Path(__file__).resolve().parents[3] / "typescript" / "tests" / "fixtures"
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_transaction_fixture_round_trips():
    raw = _load("merchant-transaction.json")
    tx = from_wire(Transaction, raw)
    assert tx.status == "failed"
    assert tx.type == "collection"
    assert tx.failure_code == "insufficient_balance"
    assert "INSUFFICIENT_BALANCE" not in (tx.failure_reason or "")
    assert tx.operator_tid == "TEST_AABBCCDD"


def test_webhook_fixture_has_collection_and_legacy_type():
    raw = _load("merchant-webhook.json")
    snapshot = WebhookTransactionSnapshot(**raw)
    assert snapshot.type == "collection"
    assert snapshot.legacyType == "charge"
    assert snapshot.failureCode == "insufficient_balance"


def test_invoice_fixture_keeps_payment_link_and_null_number():
    raw = _load("merchant-invoice.json")
    invoice = from_wire(InvoiceResponse, raw)
    assert "/pay?token=" in invoice.payment_link
    assert invoice.url == invoice.payment_link
    assert invoice.invoice_number is None
