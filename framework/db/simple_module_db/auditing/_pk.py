"""Primary-key rendering shared by audit capture and its readers."""

from __future__ import annotations

import re
import uuid

_UUID_PK_PART = r"UUID\('([^']+)'\)"
_UUID_COMPOSITE_PK = re.compile(rf"\({_UUID_PK_PART}(?:, {_UUID_PK_PART})+\)")


def format_pk(values: tuple | list) -> str:
    """One primary-key rendering for ``entity_id``: bare value, or a tuple string."""
    if len(values) == 1:
        return str(values[0]) if values[0] is not None else ""
    return str(tuple(values))


def parse_uuid_pk(value: str) -> tuple[uuid.UUID, ...] | None:
    """Read composite UUID keys from ``format_pk``; unsupported ids return None."""
    if _UUID_COMPOSITE_PK.fullmatch(value) is None:
        return None
    try:
        return tuple(uuid.UUID(part) for part in re.findall(_UUID_PK_PART, value))
    except ValueError:
        return None
