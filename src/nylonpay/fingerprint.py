"""Stable server fingerprint based on OS metadata.

WHAT IT IS: an opaque, stable identifier for the machine this process runs
on. It is sent as ``_fingerprint`` in the request body and is the first
component of ``signatureInput``, so the value signed and the value sent
must be identical.

WHAT IT IS NOT: it does not bind a signature to a machine. The server
reads ``_fingerprint`` out of the body and feeds that value into its own
HMAC; it never computes one of its own and has no way to. A replayed
request carries the same fingerprint it was signed with, so replay is
prevented by the nonce and timestamp, not by this value.

Because the server treats it as opaque, what goes into the hash is an
implementation choice. It can change without breaking older clients, which
sign with whatever they sent, and the SDKs do not need to agree with each
other on the inputs.

Only OS-level inputs are used. Python version and implementation were
removed on 2026-09-08: a runtime version is not something every SDK can
obtain the same way, and it made the value churn on every upgrade for no
benefit.
"""

from __future__ import annotations

import hashlib
import platform
import socket
from functools import lru_cache


@lru_cache(maxsize=1)
def generate_fingerprint() -> str:
    """Derive a SHA-256 hex digest from OS metadata.

    Cached after first call — the environment cannot change within a
    running process, so recomputing is wasteful.
    """
    components = "|".join(
        [
            f"type:{platform.system()}",
            f"platform:{platform.platform()}",
            f"arch:{platform.machine()}",
            f"release:{platform.release()}",
            f"hostname:{socket.gethostname()}",
        ]
    )
    return hashlib.sha256(components.encode()).hexdigest()
