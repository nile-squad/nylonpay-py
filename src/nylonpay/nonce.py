"""Cryptographic nonce generation for SDK request deduplication.

WHY a separate module: the nonce is a core security primitive used in
every signed request. Isolating it keeps the generation strategy
(swappable for testing) and the byte-length → hex-length relationship
in one place.
"""

from __future__ import annotations

import secrets


def generate_nonce(length: int = 16) -> str:
    """Produce a cryptographically secure random hex string.

    The default 16-byte (32 hex char) nonce provides sufficient entropy
    for replay-attack prevention within the backend's freshness window.
    Uses ``secrets.token_hex`` which delegates to the OS CSPRNG.
    """
    return secrets.token_hex(length)
