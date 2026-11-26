"""Build a JSON request body from ``--json/--file/--set/--set-json`` input."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from simple_module_remote.generate.pairs import split_pair
from simple_module_remote.output.reasons import os_reason
from simple_module_remote.schema.loader import resolve_ref, unwrap_nullable

__all__ = ["BodyError", "body_field_summary", "build_json_body", "missing_required"]

STDIN = "-"
_TRUE = frozenset({"true", "1", "yes"})
_FALSE = frozenset({"false", "0", "no"})


class BodyError(Exception):
    """Invalid request-body input; the message names the offending flag or key."""


def _read_text(source: str, stdin: TextIO, flag: str) -> str:
    if source == STDIN:
        return stdin.read().removeprefix("\ufeff")
    try:
        return Path(source).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise BodyError(f"{flag}: cannot read {source}: {os_reason(exc)}") from None


def _reject_constant(name: str) -> object:
    raise ValueError(name)


def _finite_float(text: str) -> float:
    number = float(text)
    if not math.isfinite(number):  # 1e999 overflows to infinity
        raise ValueError(text)
    return number


def _parse_json(text: str, flag: str) -> object:
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_float=_finite_float)
    except json.JSONDecodeError as exc:
        raise BodyError(f"{flag}: invalid JSON ({exc.msg} at position {exc.pos})") from None
    except ValueError as exc:  # NaN, Infinity and -Infinity are not JSON
        raise BodyError(f"{flag}: invalid JSON ({exc} is not allowed)") from None


def _property_schema(root: dict, schema: dict | None, parts: Sequence[str]) -> dict | None:
    current = schema
    for part in parts:
        if current is None:
            return None
        props = resolve_ref(root, current).get("properties")
        nxt = props.get(part) if isinstance(props, dict) else None
        current = nxt if isinstance(nxt, dict) else None
    return resolve_ref(root, current) if current is not None else None


def _type_of(schema: dict | None, root: dict) -> str | None:
    if not schema:
        return None
    schema = unwrap_nullable(root, schema)
    declared = schema.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if t != "null"), None)
    return declared if isinstance(declared, str) else None


def _coerce(raw: str, key: str, schema: dict | None, root: dict) -> object:
    kind = _type_of(schema, root)
    try:
        if kind == "integer":
            return int(raw)
        if kind == "number":
            number = float(raw)
            if not math.isfinite(number):
                raise ValueError(raw)
            return number
    except ValueError:
        raise BodyError(f"--set {key}: expected {kind}, got {raw!r}") from None
    if kind == "array":
        # One element, coerced by the items schema; repeat --set to add more (or --set-json).
        items = unwrap_nullable(root, schema).get("items") if schema else None
        element = resolve_ref(root, items) if isinstance(items, dict) else None
        return [_coerce(raw, key, element, root)]
    if kind == "boolean":
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise BodyError(f"--set {key}: expected boolean (true/false), got {raw!r}")
    return raw


def _existing(body: dict, key: str) -> list | None:
    """The list currently at ``key`` (dotted), or ``None`` when it is not a list."""
    node: object = body
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node if isinstance(node, list) else None


def _related(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _assign(target: dict, key: str, value: object, flag: str) -> None:
    parts = key.split(".")
    if not all(parts):
        raise BodyError(f"{flag} {key}: empty path segment")
    node = target
    for part in parts[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise BodyError(f"{flag} {key}: {part!r} is not an object")
        node = child
    node[parts[-1]] = value


def _set_value(raw: str, key: str, stdin: TextIO, schema: dict | None, root: dict) -> object:
    if raw.startswith("@"):
        text = _read_text(raw[1:], stdin, f"--set {key}")
        return text.removesuffix("\n").removesuffix("\r")
    if raw == "null":
        return None
    return _coerce(raw, key, schema, root)


def build_json_body(
    *,
    json_arg: str | None,
    file_arg: str | None,
    sets: Sequence[str],
    set_jsons: Sequence[str],
    body_schema: dict | None,
    root: dict,
    stdin: TextIO,
) -> dict | list | None:
    """Merge json -> file -> set-json -> set; ``None`` when no input was given."""
    stdin_users = (file_arg == STDIN) + sum(1 for s in sets if s.partition("=")[2] == f"@{STDIN}")
    if stdin_users > 1:
        raise BodyError("--file - and --set key=@- cannot both read stdin in one command")
    if json_arg is None and file_arg is None and not sets and not set_jsons:
        return None

    body: object = {}
    if json_arg is not None:
        body = _parse_json(json_arg, "--json")
    if file_arg is not None:
        loaded = _parse_json(_read_text(file_arg, stdin, "--file"), "--file")
        if isinstance(body, dict) and isinstance(loaded, dict) and json_arg is not None:
            body = {**body, **loaded}
        else:
            body = loaded
    if not isinstance(body, dict | list):
        raise BodyError("request body must be a JSON object or array")
    expected = _type_of(body_schema, root)
    if expected == "object" and isinstance(body, list):
        raise BodyError("this command takes a JSON object, but --json/--file gave an array")
    if (sets or set_jsons) and not isinstance(body, dict):
        raise BodyError("--set/--set-json need an object body, but --json/--file gave an array")
    if isinstance(body, dict):
        for item in set_jsons:
            key, raw = split_pair(item, "--set-json", BodyError)
            _assign(body, key, _parse_json(raw, f"--set-json {key}"), "--set-json")
        arrays: set[str] = set()
        for item in sets:
            key, raw = split_pair(item, "--set", BodyError)
            schema = _property_schema(root, body_schema, key.split("."))
            value = _set_value(raw, key, stdin, schema, root)
            current = _existing(body, key) if key in arrays else None
            if current is not None and isinstance(value, list):
                current.extend(value)  # a repeated --set on an array field adds an element
                continue
            # Replacing a field (or an ancestor) ends any array being accumulated under it.
            arrays = {a for a in arrays if not _related(a, key)}
            _assign(body, key, value, "--set")
            if _type_of(schema, root) == "array" and isinstance(value, list):
                arrays.add(key)
    return body


def missing_required(body: dict, body_schema: dict | None, root: dict) -> list[str]:
    """Top-level required property names absent from ``body``."""
    if not body_schema:
        return []
    required = resolve_ref(root, body_schema).get("required")
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str) and name not in body]


MAX_HELP_FIELDS = 40


def _type_label(root: dict, prop: object) -> str:
    if not isinstance(prop, dict):
        return "any"
    node = unwrap_nullable(root, resolve_ref(root, prop))
    kind = node.get("type")
    if kind == "array":
        items = node.get("items")
        return f"list of {_type_label(root, items)}" if isinstance(items, dict) else "list"
    if isinstance(kind, str):
        return kind
    return "object" if "properties" in node else "any"


def body_field_summary(body_schema: dict | None, root: dict) -> list[tuple[str, str, bool]]:
    """``(name, type, required)`` for each top-level body field, for ``--help`` (#1241)."""
    if not body_schema:
        return []
    schema = resolve_ref(root, body_schema)
    props = schema.get("properties")
    if not isinstance(props, dict):
        return []
    required = schema.get("required")
    wanted = set(required) if isinstance(required, list) else set()
    return [
        (name, _type_label(root, prop), name in wanted)
        for name, prop in list(props.items())[:MAX_HELP_FIELDS]
        if isinstance(name, str) and not (isinstance(prop, dict) and prop.get("readOnly"))
    ]
