"""Wire format conversion between Python dataclasses and backend JSON.

Python dataclasses use snake_case field names (idiomatic Python), but the
backend JSON wire format uses camelCase (matching the API spec). This
module handles the conversion at the transport boundary so domain code
stays idiomatic Python while the wire payload matches what the backend
expects.

The conversion is bidirectional: ``to_wire`` for outgoing requests
(snake_case → camelCase), ``from_wire`` for incoming responses
(camelCase → snake_case). Nested dataclasses are handled recursively
so merchants never see camelCase in their code.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, get_type_hints

_CAMEL_RE = re.compile(r"([A-Z])")


def snake_to_camel(s: str) -> str:
    """Convert snake_case to camelCase.

    e.g. ``'phone_number'`` → ``'phoneNumber'``, ``'api_key'`` → ``'apiKey'``.
    """
    parts = s.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def camel_to_snake(s: str) -> str:
    """Convert camelCase to snake_case.

    e.g. ``'phoneNumber'`` → ``'phone_number'``, ``'updatedAt'`` → ``'updated_at'``.
    """
    return _CAMEL_RE.sub(r"_\1", s).lower().lstrip("_")


def to_wire(obj: Any) -> Any:
    """Convert a dataclass instance or dict to a camelCase dict for the wire payload.

    Recursively converts nested dataclasses and dicts. Lists are processed
    element-by-element. Non-dataclass, non-dict values pass through unchanged.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_wire(dataclasses.asdict(obj))

    if isinstance(obj, dict):
        return {snake_to_camel(k): to_wire(v) for k, v in obj.items() if v is not None}

    if isinstance(obj, list):
        return [to_wire(item) for item in obj]

    return obj


def from_wire(cls: type, data: dict[str, Any]) -> Any:
    """Construct a dataclass instance from a camelCase dict.

    Converts keys to snake_case, filters to only fields the dataclass accepts,
    and constructs the instance. Handles nested dataclasses for known field
    types resolved via ``typing.get_type_hints``.
    """
    if not dataclasses.is_dataclass(cls):
        return data

    valid_fields = {f.name for f in dataclasses.fields(cls)}
    hints = get_type_hints(cls)

    snake_data: dict[str, Any] = {}
    for key, value in data.items():
        snake_key = camel_to_snake(key)
        if snake_key not in valid_fields:
            continue

        field_type = hints.get(snake_key)
        if (
            field_type is not None
            and dataclasses.is_dataclass(field_type)
            and isinstance(value, dict)
        ):
            snake_data[snake_key] = from_wire(field_type, value)
        else:
            snake_data[snake_key] = value

    return cls(**snake_data)
