"""Lightweight event emitter for payment lifecycle events.

WHY a custom emitter: the SDK needs pub/sub for payment status
transitions (``processing``, ``success``, ``failed``, etc.) without
pulling in a third-party dependency. The emitter is a closure-based
factory — no classes, no inheritance — returning a dict of functions
that share private listener state.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from .slang import Result


@runtime_checkable
class Emitter(Protocol):
    """Contract for the object returned by ``create_emitter``."""

    def on(self, event: str, handler: Callable[..., None]) -> Callable[[], None]:
        """Register a handler. Returns an unsubscribe function."""
        ...

    def once(self, event: str, handler: Callable[..., None]) -> Any:
        """Register a handler that auto-unsubscribes after first invocation."""
        ...

    def off(self, event: str, handler: Callable[..., None]) -> None:
        """Remove a handler. Safe to call for unregistered handlers."""
        ...

    def emit(self, event: str, data: Any) -> None:
        """Invoke all handlers for ``event`` with ``data``. Swallows exceptions."""
        ...

    def clear(self, event: str | None = None) -> None:
        """Remove all handlers for one event, or all events if ``event`` is None."""
        ...

    def listener_count(self, event: str) -> int:
        """Return the number of registered handlers for ``event``."""
        ...


def create_emitter() -> dict[str, Any]:
    """Create a new event emitter with private listener state.

    Returns a dict of functions (``on``, ``once``, ``off``, ``emit``,
    ``clear``, ``listener_count``) that share a closure over the
    listeners map. Handler collections use ``dict[Callable, None]``
    instead of ``set`` to preserve insertion order (Python 3.7+
    guarantee) while providing O(1) add/remove.
    """
    listeners: dict[str, dict[Callable[..., None], None]] = {}

    _MAX_HANDLERS_PER_EVENT = 1000

    def on(event: str, handler: Callable[..., None]) -> Callable[[], None]:
        """Register ``handler`` for ``event``. Returns an unsubscribe closure."""
        if event not in listeners:
            listeners[event] = {}
        if len(listeners[event]) >= _MAX_HANDLERS_PER_EVENT:
            return lambda: off(event, handler)
        listeners[event][handler] = None
        return lambda: off(event, handler)

    def once(event: str, handler: Callable[..., None]) -> dict[str, Any]:
        """Register ``handler`` to fire at most once, then auto-unsubscribe."""

        def wrapper(data: Any) -> None:
            off(event, wrapper)
            handler(data)

        on(event, wrapper)
        return emitter

    def off(event: str, handler: Callable[..., None]) -> None:
        """Remove ``handler`` from ``event``. No-op if not registered."""
        listeners.get(event, {}).pop(handler, None)

    def emit(event: str, data: Any) -> None:
        """Call all handlers for ``event`` in insertion order.

        Each handler is wrapped in try/except so one failure cannot
        prevent subsequent handlers from running.
        """
        handlers = listeners.get(event)
        if not handlers:
            return
        for handler in list(handlers):
            Result.try_(lambda h=handler: h(data))

    def clear(event: str | None = None) -> None:
        """Remove handlers for one event, or all events if ``event`` is None."""
        if event is not None:
            listeners.pop(event, None)
        else:
            listeners.clear()

    def listener_count(event: str) -> int:
        """Return the number of handlers registered for ``event``."""
        return len(listeners.get(event, {}))

    emitter: dict[str, Any] = {
        "on": on,
        "once": once,
        "off": off,
        "emit": emit,
        "clear": clear,
        "listener_count": listener_count,
    }
    return emitter
