"""Coercion helpers for accepting dicts at SDK boundaries.

Lets merchants pass plain dicts instead of importing and constructing
dataclasses for every nested type (Customer, Destination, BankDetails,
InvoiceItem). The coercion runs at the operation boundary so the rest
of the SDK always works with typed dataclass instances.

Example::

    # Instead of this:
    from nylonpay import Customer, CollectPaymentInput
    nylonpay.collect_payment(CollectPaymentInput(
        amount=5000, currency="UGX",
        customer=Customer(name="John", phone_number="256700000000"),
        description="Order",
    ))

    # Merchants can do this:
    nylonpay.collect_payment(
        amount=5000, currency="UGX",
        customer={"name": "John", "phone_number": "256700000000"},
        description="Order",
    )
"""

from __future__ import annotations

import dataclasses
import types
from typing import Any, get_args, get_origin, get_type_hints

_MAX_DEPTH = 32


class _DepthExceededError(Exception):
    """Raised when dict nesting exceeds the safety cap during coercion."""


def coerce_dataclass(cls: type, data: Any, depth: int = 0) -> Any:
    """Construct a dataclass from a dict, coercing nested fields recursively.

    If *data* is already a dataclass instance, returns it unchanged.
    If *data* is a dict, constructs *cls* from it, coercing any nested
    dict fields to their declared dataclass types.
    Otherwise, returns *data* unchanged.

    A depth cap prevents stack overflow on pathologically nested input.
    """
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        return data
    if not isinstance(data, dict):
        return data

    if depth > _MAX_DEPTH:
        raise _DepthExceededError(_MAX_DEPTH)

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}

    for key, value in data.items():
        field_type = hints.get(key)
        kwargs[key] = _coerce_field(field_type, value, depth + 1)

    return cls(**kwargs)


def _coerce_field(field_type: Any, value: Any, depth: int = 0) -> Any:
    """Coerce a value based on its declared field type."""
    if value is None or field_type is None:
        return value

    if isinstance(field_type, types.UnionType):
        for arg in get_args(field_type):
            if arg is type(None):
                continue
            if dataclasses.is_dataclass(arg) and isinstance(value, dict):
                return coerce_dataclass(arg, value, depth)
            if get_origin(arg) is list:
                return _coerce_list(arg, value, depth)
        return value

    if get_origin(field_type) is list:
        return _coerce_list(field_type, value, depth)

    if dataclasses.is_dataclass(field_type) and isinstance(value, dict):
        return coerce_dataclass(field_type, value, depth)

    return value


def _coerce_list(list_type: Any, value: Any, depth: int = 0) -> Any:
    """Coerce a list of dicts to a list of dataclass instances."""
    if not isinstance(value, list):
        return value

    args = get_args(list_type)
    element_type = args[0] if args else None
    if element_type is None or not dataclasses.is_dataclass(element_type):
        return value

    return [
        coerce_dataclass(element_type, item, depth) if isinstance(item, dict) else item
        for item in value
    ]
