"""Unit tests for SDK operations (validation + transport integration).

Uses ``httpx.MockTransport`` so the network is fully mocked. Each test
either:
- Triggers a synchronous validation throw (no transport interaction), or
- Drives an operation and asserts the outgoing request + parsed response.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest

from nylonpay import (
    VerifyWebhookInput,
    create_nylon_pay,
    verify_webhook_signature,
)
from nylonpay.signature import create_canonical_payload
from nylonpay.transport import SdkException

API_KEY = "npk_test_sdk_unit"
API_SECRET = "nps_test_sdk_unit_secret"


def _sign(data: dict, secret: str = API_SECRET) -> str:
    return hmac.new(
        secret.encode(),
        create_canonical_payload(data).encode(),
        hashlib.sha256,
    ).hexdigest()


def _success_response(data: dict) -> dict:
    """Build a wire response with a valid signature for ``data``."""
    sig = _sign(data)
    return {"status": True, "message": "ok", "data": {**data, "_responseSignature": sig}}


@pytest.fixture
def captured():
    return {}


def _make_sdk(handler) -> tuple[Any, httpx.Client, dict]:
    """Build a mock-transport SDK. Caller owns the returned client."""
    captured: dict = {}

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        try:
            captured["body"] = json.loads(request.content) if request.content else None
        except (ValueError, TypeError):
            captured["body"] = None
        return handler(request, captured)

    transport = httpx.MockTransport(wrapped)
    client = httpx.Client(transport=transport)
    sdk = create_nylon_pay(
        api_key=API_KEY,
        api_secret=API_SECRET,
        base_url="https://api.test/services",
        max_retries=0,
        timeout_ms=1000,
        http_client=client,
        force=True,
    )
    return sdk, client, captured


def _default_handler(req, cap):
    body = cap.get("body") or {}
    payload = body.get("payload", {})
    ref = payload.get("reference", "ref_abc")
    return httpx.Response(200, json=_success_response({"reference": ref, "status": "pending"}))


def _collect_input(**overrides) -> dict[str, Any]:
    base: dict[str, Any] = {
        "amount": 1000,
        "currency": "UGX",
        "customer": {"name": "Alice", "phone_number": "+256700000000"},
        "description": "Order #1",
    }
    base.update(overrides)
    return base


# collect_payment --------------------------------------------------------------


def test_collect_payment_returns_payment_instance(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        inst = sdk.collect_payment(**_collect_input())
        assert inst.reference is not None
        assert inst.status == "pending"
    finally:
        client.close()


def test_collect_payment_normalizes_phone_in_wire(captured):
    sdk, client, cap = _make_sdk(_default_handler)
    try:
        sdk.collect_payment(
            **_collect_input(customer={"name": "A", "phone_number": "+256 700 000 000"})
        )
        wire_phone = cap["body"]["payload"]["customer"]["phoneNumber"]
        # No leading "0" or "+", no whitespace; starts with 256
        assert not wire_phone.startswith("0")
        assert not wire_phone.startswith("+")
        assert " " not in wire_phone
        assert wire_phone.startswith("256")
    finally:
        client.close()


def test_collect_payment_auto_generates_reference_if_omitted(captured):
    sdk, client, cap = _make_sdk(_default_handler)
    try:
        inp = _collect_input(reference=None)
        inst = sdk.collect_payment(**inp)
        # Auto-gen reference is 15-char hex
        assert len(inst.reference) == 15
        assert all(c in "0123456789abcdef" for c in inst.reference)
        # And it's the one on the wire
        assert cap["body"]["payload"]["reference"] == inst.reference
    finally:
        client.close()


def test_collect_payment_sub_min_amount_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        inp = _collect_input(amount=100)  # < 500 minimum
        with pytest.raises(SdkException) as exc:
            sdk.collect_payment(**inp)
        assert exc.value.category == "validation"
    finally:
        client.close()


def test_collect_payment_empty_name_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        inp = _collect_input(customer={"name": "", "phone_number": "+256700000000"})
        with pytest.raises(SdkException) as exc:
            sdk.collect_payment(**inp)
        assert exc.value.category == "validation"
    finally:
        client.close()


def test_collect_payment_bad_phone_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        # Too short to be valid
        inp = _collect_input(customer={"name": "A", "phone_number": "123"})
        with pytest.raises(SdkException) as exc:
            sdk.collect_payment(**inp)
        assert exc.value.category == "validation"
    finally:
        client.close()


def test_collect_payment_reference_too_long_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        inp = _collect_input(reference="x" * 20)
        with pytest.raises(SdkException) as exc:
            sdk.collect_payment(**inp)
        assert exc.value.category == "validation"
    finally:
        client.close()


def test_collect_payment_bank_method_without_details_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        inp = _collect_input(method="bank", bank=None)
        with pytest.raises(SdkException) as exc:
            sdk.collect_payment(**inp)
        assert exc.value.category == "validation"
    finally:
        client.close()


# get_status -------------------------------------------------------------------


def test_get_status_returns_snake_case_fields(captured):
    def handler(req, cap):
        return httpx.Response(
            200,
            json=_success_response(
                {
                    "reference": "ref_1",
                    "status": "pending",
                    "amount": 1000,
                    "currency": "UGX",
                    "updatedAt": "2024-01-01T00:00:00Z",
                }
            ),
        )

    sdk, client, _ = _make_sdk(handler)
    try:
        result = sdk.get_status(reference="ref_1")
        assert result.is_ok
        r = result.value
        assert r.reference == "ref_1"
        assert r.status == "pending"
        assert r.amount == 1000
        assert r.currency == "UGX"
        assert r.updated_at == "2024-01-01T00:00:00Z"
    finally:
        client.close()


# get_transaction --------------------------------------------------------------


def test_get_transaction_returns_snake_case_fields(captured):
    tx = {
        "id": "tx-1",
        "reference": "ref_1",
        "amount": 1000,
        "currency": "UGX",
        "status": "successful",
        "type": "collection",
        "method": "mobileMoney",
        "description": "Order",
        "phone": "256700000000",
        "email": "a@b.c",
        "failureReason": None,
        "metadata": {"orderId": "123"},
        "mode": "live",
        "createdAt": "2024-01-01",
        "updatedAt": "2024-01-02",
        "operatorTid": "op-1",
    }

    def handler(req, cap):
        return httpx.Response(200, json=_success_response(tx))

    sdk, client, _ = _make_sdk(handler)
    try:
        result = sdk.get_transaction(reference="ref_1")
        assert result.is_ok
        t = result.value
        assert t.id == "tx-1"
        assert t.reference == "ref_1"
        assert t.failure_reason is None
        assert t.method == "mobileMoney"
        assert t.operator_tid == "op-1"
        assert t.created_at == "2024-01-01"
        assert t.updated_at == "2024-01-02"
    finally:
        client.close()


def test_get_transaction_requires_id_or_reference(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        with pytest.raises(SdkException) as exc:
            sdk.get_transaction()
        assert exc.value.category == "validation"
    finally:
        client.close()


# verify_phone -----------------------------------------------------------------


def test_verify_phone_normalizes_phone_in_wire(captured):
    def handler(req, cap):
        return httpx.Response(
            200,
            json=_success_response(
                {
                    "phoneNumber": "256700000000",
                    "customerName": "Alice",
                    "verified": True,
                }
            ),
        )

    sdk, client, cap = _make_sdk(handler)
    try:
        sdk.verify_phone(phone_number="+256 700 000 000")
        wire_phone = cap["body"]["payload"]["phoneNumber"]
        assert not wire_phone.startswith("+")
        assert " " not in wire_phone
        assert wire_phone.startswith("256")
    finally:
        client.close()


# create_invoice ---------------------------------------------------------------


def test_create_invoice_auto_generates_reference(captured):
    def handler(req, cap):
        body = cap["body"]
        ref = body["payload"]["reference"]
        return httpx.Response(
            200,
            json=_success_response(
                {
                    "id": "inv_1",
                    "url": "https://pay.test/i/abc",
                    "token": "tok_abc",
                    "expiresAt": "2024-12-31",
                    "status": "pending",
                    "reference": ref,
                }
            ),
        )

    sdk, client, cap = _make_sdk(handler)
    try:
        result = sdk.create_invoice(amount=1000, currency="UGX", description="Invoice")
        assert result.is_ok
        assert result.value.id == "inv_1"
        assert result.value.status == "pending"
        # Reference was auto-generated (15 hex)
        wire_ref = cap["body"]["payload"]["reference"]
        assert len(wire_ref) == 15
    finally:
        client.close()


def test_create_invoice_validates_amount(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        with pytest.raises(SdkException) as exc:
            sdk.create_invoice(amount=100, currency="UGX", description="x")
        assert exc.value.category == "validation"
    finally:
        client.close()


def test_create_invoice_items_negative_quantity_throws(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        with pytest.raises(SdkException) as exc:
            sdk.create_invoice(
                amount=1000,
                currency="UGX",
                description="x",
                items=[{"name": "x", "quantity": -1, "unit_price": 100}],
            )
        assert exc.value.category == "validation"
    finally:
        client.close()


# verify_webhook_signature ----------------------------------------------------


def test_verify_webhook_signature_delegates_to_standalone(captured):
    sdk, client, _ = _make_sdk(_default_handler)
    try:
        body = json.dumps({"timestamp": "1700000000000", "data": "x"}).encode()
        sig = hmac.new(API_SECRET.encode(), body, hashlib.sha256).hexdigest()
        inp = VerifyWebhookInput(
            payload=body, signature=sig, secret=API_SECRET, tolerance_seconds=0
        )
        # Standalone
        standalone_result = verify_webhook_signature(inp)
        # Via SDK (kwargs form)
        sdk_result = sdk.verify_webhook_signature(
            payload=body, signature=sig, secret=API_SECRET, tolerance_seconds=0
        )
        assert standalone_result is True
        assert sdk_result == standalone_result
    finally:
        client.close()
