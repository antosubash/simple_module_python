"""Build a JSON request body from ``--json/--file/--set/--set-json`` input."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from simple_module_remote.schema.loader import resolve_ref

__all__ = ["BodyError", "build_json_body", "missing_required"]

STDIN = "-"
_TRUE = frozenset({"true", "1", "yes"})
_FALSE = frozenset({"false", "0", "no"})


class BodyError(Exception):
    """Invalid request-body input; the message names the offending flag or key."""


def _read_text(source: str, stdin: TextIO, flag: str) -> str:
    if source == STDIN:
        return stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BodyError(f"{flag}: cannot read {source}: {exc.__class__.__name__}") from None


def _parse_json(text: str, flag: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BodyError(f"{flag}: invalid JSON ({exc.msg} at position {exc.pos})") from None


def _split(item: str, flag: str) -> tuple[str, str]:
    key, sep, value = item.partition("=")
    if not sep or not key:
        raise BodyError(f"{flag}: expected key=value, got {item!r}")
    return key, value


def _property_schema(root: dict, schema: dict | None, parts: Sequence[str]) -> dict | None:
    current = schema
    for part in parts:
        if current is None:
            return None
        props = resolve_ref(root, current).get("properties")
        nxt = props.get(part) if isinstance(props, dict) else None
        current = nxt if isinstance(nxt, dict) else None
    return resolve_ref(root, current) if current is not None else None


def _type_of(schema: dict | None) -> str | None:
    if not schema:
        return None
    declared = schema.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if t != "null"), None)
    return declared if isinstance(declared, str) else None


def _coerce(raw: str, key: str, schema: dict | None) -> object:
    kind = _type_of(schema)
    try:
        if kind == "integer":
            return int(raw)
        if kind == "number":
            return float(raw)
    except ValueError:
        raise BodyError(f"--set {key}: expected {kind}, got {raw!r}") from None
    if kind == "boolean":
        lowered = raw.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise BodyError(f"--set {key}: expected boolean (true/false), got {raw!r}")
    return raw


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


def _set_value(raw: str, key: str, stdin: TextIO, schema: dict | None) -> object:
    if raw.startswith("@"):
        text = _read_text(raw[1:], stdin, f"--set {key}")
        return text[:-1] if text.endswith("\n") else text
    if raw == "null":
        return None
    return _coerce(raw, key, schema)


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
    if (sets or set_jsons) and not isinstance(body, dict):
        raise BodyError("--set/--set-json need an object body, but --json/--file gave an array")
    if isinstance(body, dict):
        for item in set_jsons:
            key, raw = _split(item, "--set-json")
            _assign(body, key, _parse_json(raw, f"--set-json {key}"), "--set-json")
        for item in sets:
            key, raw = _split(item, "--set")
            schema = _property_schema(root, body_schema, key.split("."))
            _assign(body, key, _set_value(raw, key, stdin, schema), "--set")
    return body


def missing_required(body: dict, body_schema: dict | None, root: dict) -> list[str]:
    """Top-level required property names absent from ``body``."""
    if not body_schema:
        return []
    required = resolve_ref(root, body_schema).get("required")
    if not isinstance(required, list):
        return []
    return [name for name in required if isinstance(name, str) and name not in body]
