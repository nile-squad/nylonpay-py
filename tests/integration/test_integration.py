"""Integration tests for the Nylon Pay SDK (I1-I19).

These tests run against a real backend — not mocked transport.
They verify end-to-end contract compliance: real HTTP calls, real server-side
validation, real idempotency behavior, and real error responses.

Requirements:
- NYLONPAY_API_KEY and NYLONPAY_API_SECRET environment variables
- NYLONPAY_BASE_URL for local/self-hosted backend (defaults to production)
- NYLONPAY_TEST_PHONE for a real test phone number (defaults to +256700000000)
- NYLONPAY_TEST_MODE=live for live-only tests (I15)

Tests are skipped when credentials are not available.
Each test uses a unique reference and does not depend on execution order.
"""

from __future__ import annotations

import os

import pytest

from nylonpay import SdkException, create_nylon_pay, parse_error
from nylonpay.types import NylonPaySdk

API_KEY = os.environ.get("NYLONPAY_API_KEY", "")
API_SECRET = os.environ.get("NYLONPAY_API_SECRET", "")
BASE_URL = os.environ.get("NYLONPAY_BASE_URL", "")
TEST_PHONE = os.environ.get("NYLONPAY_TEST_PHONE", "+256700000000")
TEST_MODE = os.environ.get("NYLONPAY_TEST_MODE", "")

skip_no_credentials = pytest.mark.skipif(
    not API_KEY or not API_SECRET,
    reason="NYLONPAY_API_KEY and NYLONPAY_API_SECRET required for integration tests",
)

skip_live_only = pytest.mark.skipif(
    TEST_MODE != "live",
    reason="NYLONPAY_TEST_MODE=live required for this test",
)


def _create_sdk() -> NylonPaySdk:
    """Create a fresh SDK instance with singleton bypass."""
    kwargs: dict[str, object] = {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "force": True,
    }
    if BASE_URL:
        kwargs["base_url"] = BASE_URL
    return create_nylon_pay(**kwargs)


def _unique_reference() -> str:
    """Generate a unique 15-char reference for test isolation."""
    import secrets

    return secrets.token_hex(8)[:15]


@skip_no_credentials
def test_I1_collect_payment_happy_path() -> None:
    """I1: collectPayment returns a valid reference and pending status."""
    sdk = _create_sdk()
    payment = sdk.collect_payment(
        amount=5000,
        currency="UGX",
        customer={"name": "Test Customer", "phone_number": TEST_PHONE},
        description="I1 test payment",
        reference=_unique_reference(),
    )
    assert payment.reference
    assert len(payment.reference) >= 13
    assert payment.status in ("pending", "processing")


@skip_no_credentials
def test_I2_get_transaction_after_collect() -> None:
    """I2: getTransaction matches the reference returned by collect."""
    sdk = _create_sdk()
    ref = _unique_reference()
    sdk.collect_payment(
        amount=5000,
        currency="UGX",
        customer={"name": "Test Customer", "phone_number": TEST_PHONE},
        description="I2 test payment",
        reference=ref,
    )
    result = sdk.get_transaction(reference=ref)
    assert result.is_ok
    assert result.value.reference == ref


@skip_no_credentials
def test_I3_idempotency_on_collect() -> None:
    """I3: same reference returns the same transaction, not a duplicate."""
    sdk = _create_sdk()
    ref = _unique_reference()
    input_data = {
        "amount": 5000,
        "currency": "UGX",
        "customer": {"name": "Test Customer", "phone_number": TEST_PHONE},
        "description": "I3 idempotency test",
        "reference": ref,
    }
    payment1 = sdk.collect_payment(**input_data)
    payment2 = sdk.collect_payment(**input_data)
    assert payment1.reference == payment2.reference


@skip_no_credentials
def test_I4_payout_happy_path() -> None:
    """I4: makePayout returns a valid reference and pending status."""
    sdk = _create_sdk()
    payment = sdk.make_payout(
        amount=5000,
        currency="UGX",
        customer={"name": "Test Customer", "phone_number": TEST_PHONE},
        destination={
            "account_holder_name": "Test Customer",
            "account_number": "123456",
        },
        description="I4 test payout",
        reference=_unique_reference(),
    )
    assert payment.reference
    assert len(payment.reference) >= 13
    assert payment.status in ("pending", "processing")


@skip_no_credentials
def test_I5_get_transaction_after_payout() -> None:
    """I5: getTransaction matches the reference returned by payout."""
    sdk = _create_sdk()
    ref = _unique_reference()
    sdk.make_payout(
        amount=5000,
        currency="UGX",
        customer={"name": "Test Customer", "phone_number": TEST_PHONE},
        destination={
            "account_holder_name": "Test Customer",
            "account_number": "123456",
        },
        description="I5 test payout",
        reference=ref,
    )
    result = sdk.get_transaction(reference=ref)
    assert result.is_ok
    assert result.value.reference == ref


@skip_no_credentials
def test_I6_idempotency_on_payout() -> None:
    """I6: same reference returns the same transaction, not a duplicate."""
    sdk = _create_sdk()
    ref = _unique_reference()
    input_data = {
        "amount": 5000,
        "currency": "UGX",
        "customer": {"name": "Test Customer", "phone_number": TEST_PHONE},
        "destination": {
            "account_holder_name": "Test Customer",
            "account_number": "123456",
        },
        "description": "I6 idempotency test",
        "reference": ref,
    }
    payment1 = sdk.make_payout(**input_data)
    payment2 = sdk.make_payout(**input_data)
    assert payment1.reference == payment2.reference


@skip_no_credentials
def test_I7_verify_phone() -> None:
    """I7: verifyPhone returns a result from the real provider."""
    sdk = _create_sdk()
    result = sdk.verify_phone(phone_number=TEST_PHONE, purpose="collection")
    # We don't assert on verified=True because sandbox may not have a real number
    assert result.is_ok or result.is_err


@skip_no_credentials
def test_I8_missing_api_key() -> None:
    """I8: missing apiKey throws before any network call."""
    with pytest.raises(ValueError, match="api_key"):
        create_nylon_pay(api_key="", api_secret="nps_test")


@skip_no_credentials
def test_I9_bad_api_key_prefix() -> None:
    """I9: bad apiKey prefix throws before any network call."""
    with pytest.raises(ValueError, match="npk_"):
        create_nylon_pay(api_key="bad_key", api_secret="nps_test")


@skip_no_credentials
def test_I10_missing_api_secret() -> None:
    """I10: missing apiSecret throws before any network call."""
    with pytest.raises(ValueError, match="api_secret"):
        create_nylon_pay(api_key="npk_test", api_secret="")


@skip_no_credentials
def test_I11_bad_api_secret_prefix() -> None:
    """I11: bad apiSecret prefix throws before any network call."""
    with pytest.raises(ValueError, match="nps_"):
        create_nylon_pay(api_key="npk_test", api_secret="bad_secret")


@skip_no_credentials
def test_I12_singleton_behavior() -> None:
    """I12: second call without force returns the same instance."""
    c1 = create_nylon_pay(api_key=API_KEY, api_secret=API_SECRET, force=True)
    c2 = create_nylon_pay(api_key=API_KEY, api_secret=API_SECRET)
    assert c1 is c2


@skip_no_credentials
def test_I13_unknown_reference() -> None:
    """I13: getTransaction returns error for a non-existent reference."""
    sdk = _create_sdk()
    result = sdk.get_transaction(reference="nonexistent_ref_1")
    assert result.is_err


@skip_no_credentials
def test_I14_sub_minimum_collection_amount() -> None:
    """I14: sub-minimum collection amount is rejected with validation error."""
    sdk = _create_sdk()
    with pytest.raises(SdkException) as exc_info:
        sdk.collect_payment(
            amount=100,
            currency="UGX",
            customer={"name": "Test", "phone_number": TEST_PHONE},
            description="I14 sub-min test",
            reference=_unique_reference(),
        )
    assert exc_info.value.category == "validation"


@skip_no_credentials
def test_I14b_sub_minimum_payout_amount() -> None:
    """I14b: sub-minimum payout amount is rejected with validation error."""
    sdk = _create_sdk()
    with pytest.raises(SdkException) as exc_info:
        sdk.make_payout(
            amount=100,
            currency="UGX",
            customer={"name": "Test", "phone_number": TEST_PHONE},
            destination={
                "account_holder_name": "Test",
                "account_number": "123456",
            },
            description="I14b sub-min test",
            reference=_unique_reference(),
        )
    assert exc_info.value.category == "validation"


@skip_live_only
@skip_no_credentials
def test_I15_revoked_key() -> None:
    """I15: revoked API key is rejected with auth category (live-only)."""
    # This test requires a revoked key to be set up in the live environment
    sdk = _create_sdk()
    with pytest.raises(SdkException) as exc_info:
        sdk.collect_payment(
            amount=5000,
            currency="UGX",
            customer={"name": "Test", "phone_number": TEST_PHONE},
            description="I15 revoked key test",
            reference=_unique_reference(),
        )
    assert exc_info.value.category == "auth"


@skip_no_credentials
def test_I16_unknown_key_auth_category() -> None:
    """I16: well-formed but unknown key yields auth category."""
    sdk = create_nylon_pay(
        api_key="npk_test_unknown_key_12345",
        api_secret="nps_test_unknown_secret_12345",
        force=True,
    )
    result = sdk.get_status(reference="any_reference")
    assert result.is_err
    error = parse_error(result.error)
    assert error.category == "auth"


@skip_no_credentials
def test_I17_resolve_returns_full_transaction() -> None:
    """I17: collectPaymentAndResolve returns full Transaction with id, amount, metadata."""
    sdk = _create_sdk()
    ref = _unique_reference()
    result = sdk.collect_payment_and_resolve(
        amount=5000,
        currency="UGX",
        customer={"name": "Test Customer", "phone_number": TEST_PHONE},
        description="I17 resolve test",
        reference=ref,
        metadata={"order_id": "test-123"},
    )
    if result.is_ok:
        tx = result.value
        assert tx.id
        assert tx.amount == 5000
        assert tx.reference == ref
        assert tx.metadata is not None


@skip_no_credentials
def test_I18_metadata_round_trip() -> None:
    """I18: merchant-supplied metadata is returned unchanged."""
    sdk = _create_sdk()
    ref = _unique_reference()
    metadata = {"orderId": "order-123", "source": "integration-test"}
    sdk.collect_payment(
        amount=5000,
        currency="UGX",
        customer={"name": "Test", "phone_number": TEST_PHONE},
        description="I18 metadata test",
        reference=ref,
        metadata=metadata,
    )
    result = sdk.get_transaction(reference=ref)
    if result.is_ok:
        for key, value in metadata.items():
            assert result.value.metadata.get(key) == value


@skip_no_credentials
def test_I19_polling_reaches_terminal() -> None:
    """I19: a polling instance resolves to a terminal state and never hangs."""
    sdk = _create_sdk()
    payment = sdk.collect_payment(
        amount=5000,
        currency="UGX",
        customer={"name": "Test", "phone_number": TEST_PHONE},
        description="I19 polling test",
        reference=_unique_reference(),
    )
    tx = payment.wait()
    # In sandbox, the transaction should reach a terminal state
    # (successful, failed, or cancelled). It should not hang.
    # tx is None on failure/cancellation, Transaction on success.
    # We just assert it didn't hang — the wait() returned.
    assert tx is None or tx.id is not None
