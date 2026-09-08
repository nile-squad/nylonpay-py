"""Unit tests for the server fingerprint."""

from __future__ import annotations

import hashlib
import platform
import re
import socket

from nylonpay.fingerprint import generate_fingerprint


def test_returns_64_char_hex():
    fp = generate_fingerprint()
    assert len(fp) == 64
    assert re.fullmatch(r"[0-9a-f]+", fp) is not None


def test_stable_within_process():
    a = generate_fingerprint()
    b = generate_fingerprint()
    assert a == b


def test_uses_only_os_metadata():
    """Pin the exact composition.

    The Python version and implementation were removed on 2026-09-08: a runtime
    version is not obtainable the same way in every SDK and churned the value on
    every upgrade. Recomputing the digest here fails the moment anything is
    added back, which a length or format check would not catch.
    """
    expected_components = "|".join(
        [
            f"type:{platform.system()}",
            f"platform:{platform.platform()}",
            f"arch:{platform.machine()}",
            f"release:{platform.release()}",
            f"hostname:{socket.gethostname()}",
        ]
    )
    expected = hashlib.sha256(expected_components.encode()).hexdigest()
    assert generate_fingerprint() == expected
