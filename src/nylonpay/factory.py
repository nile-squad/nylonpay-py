"""Factory function to create a Nylon Pay SDK instance.

Main entry point for merchants. Singleton-caches instances by
``api_key + base_url + sha256(api_secret)`` so the same credentials
return the same instance — rotating the secret yields a fresh one.
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from .config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_POLL_INTERVAL_MS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_MS,
)
from .sdk import create_sdk_instance
from .types import NylonPayConfig, NylonPaySdk

_instances: dict[str, NylonPaySdk] = {}
_instances_lock = threading.Lock()


def create_nylon_pay(**kwargs: Any) -> NylonPaySdk:
    """Create a Nylon Pay SDK instance.

    Accepts keyword arguments matching :class:`NylonPayConfig` fields.
    Returns the same instance for the same ``api_key`` + ``api_secret`` +
    ``base_url`` combination unless ``force=True`` is passed. Rotating the
    secret yields a fresh instance (secret-aware cache key).

    Raises ``ValueError`` if ``api_key`` is missing or doesn't start with
    ``npk_``, or ``api_secret`` is missing or doesn't start with ``nps_``.
    """
    config = NylonPayConfig(**kwargs)
    if not config.api_key:
        raise ValueError("api_key is required")
    if not config.api_key.startswith("npk_"):
        raise ValueError('api_key must start with "npk_"')
    if not config.api_secret:
        raise ValueError("api_secret is required")
    if not config.api_secret.startswith("nps_"):
        raise ValueError('api_secret must start with "nps_"')

    base_url = config.base_url or DEFAULT_BASE_URL
    # Hash the secret so it never sits raw in a dict key; rotating the
    # secret produces a different cache key → fresh instance.
    secret_hash = hashlib.sha256(config.api_secret.encode()).hexdigest()[:16]
    instance_key = f"{config.api_key}:{base_url}:{secret_hash}"

    if not config.force:
        with _instances_lock:
            existing = _instances.get(instance_key)
            if existing is not None:
                return existing

    resolved: dict[str, Any] = {
        "api_key": config.api_key,
        "api_secret": config.api_secret,
        "base_url": base_url,
        "timeout_ms": config.timeout_ms or DEFAULT_TIMEOUT_MS,
        "max_retries": config.max_retries or DEFAULT_MAX_RETRIES,
        "max_poll_interval_ms": config.max_poll_interval_ms or DEFAULT_MAX_POLL_INTERVAL_MS,
        "max_poll_duration_ms": config.max_poll_duration_ms,
        "max_poll_attempts": config.max_poll_attempts,
        "on_delayed": config.on_delayed or "wait",
        "http_client": config.http_client,
        "hooks": config.hooks,
    }

    instance = create_sdk_instance(resolved)
    with _instances_lock:
        _instances[instance_key] = instance
    return instance
