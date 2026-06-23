"""Unit tests for the factory singleton + config validation."""

from __future__ import annotations

import pytest

from nylonpay.factory import create_nylon_pay


def test_valid_config_creates_instance():
    sdk = create_nylon_pay(api_key="npk_test_factory_valid", api_secret="nps_test_abc")
    assert sdk is not None
    # Has the 9 expected operations
    for op in (
        "collect_payment",
        "collect_payment_and_resolve",
        "make_payout",
        "make_payout_and_resolve",
        "get_status",
        "get_transaction",
        "verify_phone",
        "create_invoice",
        "verify_webhook_signature",
    ):
        assert callable(getattr(sdk, op))


def test_missing_api_key():
    with pytest.raises(ValueError, match="api_key is required"):
        create_nylon_pay(api_key="", api_secret="nps_test_x")


def test_bad_api_key_prefix():
    with pytest.raises(ValueError, match='api_key must start with "npk_"'):
        create_nylon_pay(api_key="bad_key", api_secret="nps_test_x")


def test_missing_api_secret():
    with pytest.raises(ValueError, match="api_secret is required"):
        create_nylon_pay(api_key="npk_test_x", api_secret="")


def test_bad_api_secret_prefix():
    with pytest.raises(ValueError, match='api_secret must start with "nps_"'):
        create_nylon_pay(api_key="npk_test_x", api_secret="bad_secret")


def test_singleton_same_config_returns_same_instance():
    a = create_nylon_pay(api_key="npk_test_singleton", api_secret="nps_test_singleton")
    b = create_nylon_pay(api_key="npk_test_singleton", api_secret="nps_test_singleton")
    assert a is b


def test_force_true_returns_new_instance():
    a = create_nylon_pay(api_key="npk_test_force", api_secret="nps_test_force", force=True)
    b = create_nylon_pay(api_key="npk_test_force", api_secret="nps_test_force", force=True)
    assert a is not b


def test_different_secret_returns_different_instance():
    """Cache is secret-aware — rotating secret yields fresh instance."""
    api_key = "npk_test_secret_aware"
    a = create_nylon_pay(api_key=api_key, api_secret="nps_test_secret_a")
    b = create_nylon_pay(api_key=api_key, api_secret="nps_test_secret_b")
    assert a is not b
