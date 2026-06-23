"""Unit tests for phone normalization and validation."""

from __future__ import annotations

from nylonpay.phone import is_valid_phone_format, normalize_phone

# normalize_phone --------------------------------------------------------------


def test_normalize_strips_whitespace():
    assert normalize_phone("+256 700 000 000") == "256700000000"


def test_normalize_strips_plus():
    assert normalize_phone("+256700000000") == "256700000000"


def test_normalize_prepends_256_for_local_zero_prefix():
    assert normalize_phone("0700000000") == "256700000000"


def test_normalize_already_normalized_passes_through():
    assert normalize_phone("256700000000") == "256700000000"


def test_normalize_already_normalized_with_plus_strips_plus():
    assert normalize_phone("+256700000000") == "256700000000"


# is_valid_phone_format --------------------------------------------------------


def test_valid_9_to_15_digits():
    assert is_valid_phone_format("256700000") is True  # 9
    assert is_valid_phone_format("256700000000") is True  # 12
    assert is_valid_phone_format("123456789012345") is True  # 15


def test_too_short():
    assert is_valid_phone_format("12345678") is False  # 8
    assert is_valid_phone_format("") is False


def test_too_long():
    assert is_valid_phone_format("1234567890123456") is False  # 16


def test_non_digits():
    assert is_valid_phone_format("+256700000") is False
    assert is_valid_phone_format("256 700 000 000") is False
    assert is_valid_phone_format("abcdefghi") is False
