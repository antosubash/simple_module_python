"""Read locale catalogs and flatten nested locale dicts to dotted keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_catalog(path: Path) -> dict[str, Any]:
    """Parse a ``<locale>.json`` catalog; ValueError if it is not a JSON object."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object at the top level")
    return raw


def flatten_messages(
    nested: dict[str, Any],
    *,
    prefix: str = "",
) -> dict[str, str]:
    """Flatten a nested dict of string leaves to dotted keys.

    {"browse": {"title": "X"}} -> {"browse.title": "X"}

    Raises ValueError if any leaf is not a string.
    """
    out: dict[str, str] = {}
    for key, value in nested.items():
        composed = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_messages(value, prefix=composed))
        elif isinstance(value, str):
            out[composed] = value
        else:
            raise ValueError(
                f"Locale value at '{composed}' must be string or nested dict, "
                f"got {type(value).__name__}"
            )
    return out
