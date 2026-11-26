"""Load an OpenAPI document and resolve local ``$ref`` pointers."""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["load_schema", "resolve_ref"]


def load_schema(path: Path) -> dict:
    """Read an OpenAPI JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not an OpenAPI object")
    return data


def _lookup(schema: dict, ref: str) -> dict | None:
    if not ref.startswith("#/"):
        return None
    node: object = schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


def resolve_ref(schema: dict, node: dict) -> dict:
    """Follow a ``$ref`` chain to its target; cycles and dangling refs yield ``{}``."""
    seen: set[str] = set()
    current = node
    while isinstance(current, dict) and isinstance(current.get("$ref"), str):
        ref = current["$ref"]
        if ref in seen:
            return {}
        seen.add(ref)
        target = _lookup(schema, ref)
        if target is None:
            return {}
        current = target
    return current if isinstance(current, dict) else {}
