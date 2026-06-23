"""Result type — the SDK's error boundary primitive.

The SDK separates programmer errors from operational errors:

- **Programmer errors** (invalid config, missing required fields, bad amounts)
  are *thrown* — they're bugs the developer must fix before shipping.
- **Operational errors** (network failures, provider rejections, timeouts,
  rate limits) are *returned* as ``Result.Err`` — they're expected runtime
  conditions the caller should handle gracefully.

``Result`` makes this boundary explicit at every call site. A function
returning ``Result[Transaction, str]`` cannot silently succeed on failure —
the caller must check ``is_ok`` before accessing ``value``. This eliminates
the "forgot to check the error" class of bugs that plague exception-based
error handling in payment systems, where a missed error can mean a
fulfilled order with no payment.

``Result.try_(fn)`` is the single try/except boundary in the SDK.
All other code calls ``Result.try_`` instead of writing its own try/except.
This centralizes exception catching in one audited location rather than
scattering it across the codebase — every other module stays free of
raw exception handling.

The trailing underscore is the Python convention for names that collide
with keywords (``try`` is reserved). Same pattern as ``print_``,
``class_``, ``type_`` across the ecosystem.

The error type for ``Result.try_`` is ``Exception`` (the caught object),
not ``str`` — callers can inspect ``result.error`` for type, message,
or re-raise if needed. For operational errors returned from the backend,
the error type is ``str`` (a JSON-serialized ``SdkError`` that
``parse_error`` can decode into a structured category + message).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Result(Generic[T, E]):
    """A value that is either ok (success) or err (failure).

    Construct with ``Result.ok(value)``, ``Result.err(error)``, or
    ``Result.try_(fn)``. Never construct directly — the class methods
    enforce the invariant that exactly one of value/error is set.
    """

    _is_ok: bool
    _value: T | None = None
    _error: E | None = None

    @classmethod
    def ok(cls, value: T) -> Result[T, E]:
        """Create a successful result carrying ``value``."""
        return cls(_is_ok=True, _value=value)

    @classmethod
    def err(cls, error: E) -> Result[T, E]:
        """Create an error result carrying ``error``."""
        return cls(_is_ok=False, _error=error)

    @classmethod
    def try_(cls, fn: Callable[[], T]) -> Result[T, Exception]:
        """Wrap a callable — returns ``Ok(value)`` or ``Err(exception)``.

        Never raises. This is the SDK's single try/except boundary —
        all other code calls ``Result.try_`` instead of writing its own.

        The error type is ``Exception`` (the caught exception object),
        not ``str`` — callers can inspect ``result.error`` for type,
        message, or re-raise if needed.
        """
        try:
            return cls(_is_ok=True, _value=fn())  # ty: ignore[invalid-return-type]
        except Exception as exc:
            return cls(_is_ok=False, _error=exc)  # ty: ignore[invalid-return-type]

    @property
    def is_ok(self) -> bool:
        """True if this is a success result."""
        return self._is_ok

    @property
    def is_err(self) -> bool:
        """True if this is an error result."""
        return not self._is_ok

    @property
    def value(self) -> T:
        """The success value. Raises ``ValueError`` if accessed on an error result."""
        if not self._is_ok:
            raise ValueError("Cannot access .value on an error result")
        return self._value  # ty: ignore[invalid-return-type]

    @property
    def error(self) -> E:
        """The error value. Raises ``ValueError`` if accessed on a success result."""
        if self._is_ok:
            raise ValueError("Cannot access .error on a success result")
        return self._error  # ty: ignore[invalid-return-type]


def Ok(value: T) -> Result[T, E]:
    """Create a successful result. Convenience alias for ``Result.ok(value)``."""
    return Result(_is_ok=True, _value=value)


def Err(error: E) -> Result[T, E]:
    """Create an error result. Convenience alias for ``Result.err(error)``."""
    return Result(_is_ok=False, _error=error)
