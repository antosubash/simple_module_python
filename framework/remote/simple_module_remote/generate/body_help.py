"""The body-field summary a generated command's ``--help`` shows (#1241)."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_remote.generate.body import object_shape, type_of
from simple_module_remote.schema.loader import resolve_ref, unwrap_nullable

__all__ = ["MAX_HELP_FIELDS", "BodyField", "body_field_summary", "set_addressable"]

MAX_HELP_FIELDS = 40
# Bounds the label of a recursive array (``Tree = list of Tree``).
MAX_LABEL_DEPTH = 4
# Characters `--set key=value` reads as syntax: a dot nests, the first = splits.
# A space or any other character is fine once the shell argument is quoted.
_SET_SYNTAX = frozenset(".=")


@dataclass(frozen=True)
class BodyField:
    name: str
    kind: str
    required: bool


def set_addressable(name: str) -> bool:
    """Whether ``--set <name>=...`` reaches this field (else use ``--json``)."""
    return bool(name) and not _SET_SYNTAX.intersection(name)


def _type_label(root: dict, prop: object, depth: int = 0) -> str:
    if not isinstance(prop, dict):
        return "any"
    node = unwrap_nullable(root, resolve_ref(root, prop))
    kind = type_of(node, root)
    if kind == "array":
        items = node.get("items")
        if isinstance(items, dict) and depth < MAX_LABEL_DEPTH:
            return f"list of {_type_label(root, items, depth + 1)}"
        return "list"
    if kind is not None:
        return kind
    return "object" if "properties" in node or "allOf" in node else "any"


def body_field_summary(body_schema: dict | None, root: dict) -> tuple[list[BodyField], int]:
    """Up to :data:`MAX_HELP_FIELDS` writable top-level fields, and how many more exist."""
    if not body_schema:
        return [], 0
    props, required = object_shape(root, body_schema)
    writable = [
        (name, prop)
        for name, prop in props.items()
        if isinstance(name, str)
        and not (isinstance(prop, dict) and resolve_ref(root, prop).get("readOnly"))
    ]
    shown = [
        BodyField(name, _type_label(root, prop), name in required)
        for name, prop in writable[:MAX_HELP_FIELDS]
    ]
    return shown, len(writable) - len(shown)
