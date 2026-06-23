"""Stable server fingerprint based on the runtime environment.

WHY fingerprinting: the backend binds each signed request to the
originating server so that a leaked signature cannot be replayed from
a different machine. The fingerprint must be stable within a process
but differ across hosts, OS versions, and Python runtimes.

The components (OS type, platform, arch, release, hostname, runtime
versions) are derived from Python's ``platform`` and ``sys`` stdlib
modules. The same conceptual inputs are used across all SDK
implementations so a merchant running both TS and Python SDKs on the
same server produces comparable fingerprints.
"""

from __future__ import annotations

import hashlib
import platform
import socket
from functools import lru_cache


@lru_cache(maxsize=1)
def generate_fingerprint() -> str:
    """Derive a SHA-256 hex digest from OS and runtime metadata.

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
            f"python:{platform.python_version()}",
            f"implementation:{platform.python_implementation()}",
        ]
    )
    return hashlib.sha256(components.encode()).hexdigest()
