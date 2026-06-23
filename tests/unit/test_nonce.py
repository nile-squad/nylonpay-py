"""Unit tests for nonce generation."""

from __future__ import annotations

import re

from nylonpay.nonce import generate_nonce


def test_default_length_is_32_hex_chars():
    n = generate_nonce()
    assert len(n) == 32


def test_custom_length():
    n = generate_nonce(length=8)
    assert len(n) == 16  # 8 bytes -> 16 hex chars


def test_all_hex_chars():
    n = generate_nonce(length=64)
    assert re.fullmatch(r"[0-9a-f]+", n) is not None


def test_uniqueness_across_100_generations():
    nonces = {generate_nonce() for _ in range(100)}
    assert len(nonces) == 100
