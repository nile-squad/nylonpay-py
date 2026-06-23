"""Load .env file for integration tests.

Reads `.env` in the test directory parent (the SDK package root) and
sets environment variables before pytest collects integration tests.
No external dependency — just stdlib file parsing.
"""

from __future__ import annotations

import os
from pathlib import Path

_env_path = Path(__file__).parent.parent.parent / ".env"

if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value
