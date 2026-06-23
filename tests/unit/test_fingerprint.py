"""Unit tests for the runtime fingerprint."""

from __future__ import annotations

import re

from nylonpay.fingerprint import generate_fingerprint


def test_returns_64_char_hex():
    fp = generate_fingerprint()
    assert len(fp) == 64
    assert re.fullmatch(r"[0-9a-f]+", fp) is not None


def test_stable_within_process():
    a = generate_fingerprint()
    b = generate_fingerprint()
    assert a == b
