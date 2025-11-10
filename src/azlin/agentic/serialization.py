"""Serialization utilities for dataclasses.

This module provides helper functions to reduce duplication in to_dict() methods
across the codebase. Common patterns:
- Enum to .value
- Decimal to str
- datetime to ISO format
- Optional values handling
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def serialize_enum(value: Enum | None) -> str | None:
    """Convert Enum to its value, handling None.

    Args:
        value: Enum instance or None

    Returns:
        Enum's value as string, or None

    Example:
        >>> from enum import Enum
        >>> class Color(str, Enum):
        ...     RED = "red"
        ...     BLUE = "blue"
        >>> serialize_enum(Color.RED)
        'red'
        >>> serialize_enum(None)
        None
    """
    return value.value if value is not None else None


def serialize_decimal(value: Decimal | None) -> str | None:
    """Convert Decimal to string, handling None.

    Args:
        value: Decimal instance or None

    Returns:
        Decimal as string, or None

    Example:
        >>> from decimal import Decimal
        >>> serialize_decimal(Decimal("10.50"))
        '10.50'
        >>> serialize_decimal(None)
        None
    """
    return str(value) if value is not None else None


def serialize_datetime(value: datetime | None) -> str | None:
    """Convert datetime to ISO format, handling None.

    Args:
        value: datetime instance or None

    Returns:
        ISO format string, or None

    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2025, 1, 1, 12, 0, 0)
        >>> serialize_datetime(dt)
        '2025-01-01T12:00:00'
        >>> serialize_datetime(None)
        None
    """
    return value.isoformat() if value is not None else None


def serialize_decimal_dict(breakdown: dict[str, Decimal]) -> dict[str, str]:
    """Convert dict of Decimals to dict of strings.

    Args:
        breakdown: Dictionary with Decimal values

    Returns:
        Dictionary with string values

    Example:
        >>> from decimal import Decimal
        >>> breakdown = {"compute": Decimal("10.50"), "storage": Decimal("5.25")}
        >>> serialize_decimal_dict(breakdown)
        {'compute': '10.50', 'storage': '5.25'}
    """
    return {k: str(v) for k, v in breakdown.items()}


def serialize_enum_list(values: list[Any]) -> list[str]:
    """Convert list of Enums to list of values.

    Args:
        values: List of Enum instances

    Returns:
        List of enum values

    Example:
        >>> from enum import Enum
        >>> class Color(str, Enum):
        ...     RED = "red"
        ...     BLUE = "blue"
        >>> serialize_enum_list([Color.RED, Color.BLUE])
        ['red', 'blue']
    """
    return [v.value for v in values]


__all__ = [
    "serialize_datetime",
    "serialize_decimal",
    "serialize_decimal_dict",
    "serialize_enum",
    "serialize_enum_list",
]
