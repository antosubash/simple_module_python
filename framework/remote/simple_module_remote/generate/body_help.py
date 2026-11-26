"""The body-field summary a generated command's ``--help`` shows (#1241)."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_remote.generate.body import type_of
from simple_module_remote.schema.loader import resolve_ref, unwrap_nullable

__all__ = ["MAX_HELP_FIELDS", "BodyField", "body_field_summary", "set_addressable"]

MAX_HELP_FIELDS = 40
# A recursive array (``Tree = list of Tree``) must not recurse while building help.
MAX_LABEL_DEPTH = 4
# Characters `--set key=value` reads as syntax: a dot nests, the first = splits.
_SET_SYNTAX = frozenset(".= ")


@dataclass(frozen=True)
class BodyField:
    name: str
    kind: str
    required: bool


def set_addressable(name: str) -> bool:
    """Whether ``--set <name>=...`` reaches this field (else use ``--json``)."""
    return bool(name) and name.isprintable() and not _SET_SYNTAX.intersection(name)


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


def _object_shape(root: dict, schema: dict) -> tuple[dict, set[str]]:
    """Properties and required names of an object body, through a nullable wrapper
    and one level of ``allOf`` (how FastAPI composes models)."""
    node = unwrap_nullable(root, resolve_ref(root, schema))
    composed = node.get("allOf")
    parts = [node, *(composed if isinstance(composed, list) else [])]
    props: dict = {}
    required: set[str] = set()
    for part in parts:
        if not isinstance(part, dict):
            continue
        part = resolve_ref(root, part)
        if isinstance(found := part.get("properties"), dict):
            props.update(found)
        if isinstance(names := part.get("required"), list):
            required.update(n for n in names if isinstance(n, str))
    return props, required


def body_field_summary(body_schema: dict | None, root: dict) -> tuple[list[BodyField], int]:
    """Up to :data:`MAX_HELP_FIELDS` writable top-level fields, and how many more exist."""
    if not body_schema:
        return [], 0
    props, required = _object_shape(root, body_schema)
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
