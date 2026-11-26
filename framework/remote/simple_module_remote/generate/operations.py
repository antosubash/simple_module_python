"""Typed operation model built from an OpenAPI document."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from simple_module_remote.generate.naming import (
    RESERVED,
    command_name,
    group_name,
    valid_command_name,
)
from simple_module_remote.schema.loader import resolve_ref, unwrap_nullable

__all__ = [
    "Operation",
    "Param",
    "cli_operations",
    "find_collisions",
    "is_json_media",
    "parse_operations",
]

METHODS = ("get", "put", "post", "delete", "patch")
JSON_MEDIA = "application/json"
MULTIPART_MEDIA = "multipart/form-data"

BodyKind = Literal["none", "json", "multipart", "raw"]


@dataclass(frozen=True)
class Param:
    name: str
    location: Literal["path", "query"]
    required: bool
    schema: dict
    description: str


@dataclass(frozen=True)
class Operation:
    operation_id: str
    method: str
    path: str
    group: str
    name: str
    params: tuple[Param, ...]
    body_kind: BodyKind
    body_schema: dict | None
    summary: str
    description: str
    safe: bool
    confirm: bool
    token_capable: bool
    body_required: bool = False


def _collect_params(schema: dict, path_item: dict, op: dict) -> tuple[Param, ...]:
    merged: dict[tuple[str, str], dict] = {}
    for raw in [*path_item.get("parameters", []), *op.get("parameters", [])]:
        if not isinstance(raw, dict):
            continue
        param = resolve_ref(schema, raw)
        loc, name = param.get("in"), param.get("name")
        if loc in ("path", "query") and isinstance(name, str):
            merged[(loc, name)] = param
    params: list[Param] = []
    for (loc, name), p in merged.items():
        location: Literal["path", "query"] = "path" if loc == "path" else "query"
        params.append(
            Param(
                name=name,
                location=location,
                required=bool(p.get("required", False)) or location == "path",
                schema=unwrap_nullable(schema, resolve_ref(schema, p.get("schema") or {})),
                description=str(p.get("description") or ""),
            )
        )
    return tuple(params)


def is_json_media(media: str) -> bool:
    base = media.split(";", 1)[0].strip().lower()
    return base == JSON_MEDIA or (base.startswith("application/") and base.endswith("+json"))


def _body_required(schema: dict, op: dict) -> bool:
    return resolve_ref(schema, op.get("requestBody") or {}).get("required") is True


def _body(schema: dict, op: dict) -> tuple[BodyKind, dict | None]:
    request_body = resolve_ref(schema, op.get("requestBody") or {})
    content = request_body.get("content") or {}
    if not isinstance(content, dict) or not content:
        return "none", None
    kind: BodyKind
    json_media = next((m for m in content if isinstance(m, str) and is_json_media(m)), None)
    if json_media is not None:
        kind, media = "json", json_media
    elif MULTIPART_MEDIA in content:
        kind, media = "multipart", MULTIPART_MEDIA
    else:
        kind, media = "raw", next(iter(content))
    body_schema = (content[media] or {}).get("schema")
    return kind, resolve_ref(schema, body_schema) if isinstance(body_schema, dict) else None


def parse_operations(schema: dict) -> list[Operation]:
    """Every operation in the document, with CLI group and command names."""
    ops: list[Operation] = []
    for path, item in (schema.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            tags = op.get("tags") or []
            tag = tags[0] if tags and isinstance(tags[0], str) else None
            op_id = op.get("operationId") or f"{method}_{path}"
            override = op.get("x-cli-name")
            kind, body_schema = _body(schema, op)
            ops.append(
                Operation(
                    operation_id=op_id,
                    method=method.upper(),
                    path=path,
                    group=group_name(tag),
                    name=command_name(
                        op_id,
                        tag,
                        override if isinstance(override, str) else None,
                        method=method,
                        path=path,
                    ),
                    params=_collect_params(schema, item, op),
                    body_kind=kind,
                    body_schema=body_schema,
                    summary=str(op.get("summary") or ""),
                    description=str(op.get("description") or ""),
                    safe=op.get("x-cli-safe") is True,
                    confirm=op.get("x-cli-confirm") is True,
                    token_capable=op.get("x-sm-token") is True,
                    body_required=_body_required(schema, op),
                )
            )
    return ops


def invalid_cli_names(schema: dict) -> list[str]:
    """``x-cli-name`` values outside the command-name alphabet (shown sanitised, by repr)."""
    bad: list[str] = []
    for item in (schema.get("paths") or {}).values():
        if not isinstance(item, dict):
            continue
        for method in METHODS:
            op = item.get(method)
            name = op.get("x-cli-name") if isinstance(op, dict) else None
            if name is not None and not (isinstance(name, str) and valid_command_name(name)):
                bad.append(ascii(name)[:80])
    return bad


def cli_operations(ops: list[Operation]) -> list[Operation]:
    """Only the operations a personal access token can call."""
    return [op for op in ops if op.token_capable]


def find_collisions(ops: list[Operation]) -> list[tuple[str, str, list[str]]]:
    """``(group, name, operation_ids)`` for duplicate commands and reserved group names."""
    by_key: dict[tuple[str, str], list[str]] = {}
    for op in ops:
        by_key.setdefault((op.group, op.name), []).append(op.operation_id)
    found = [(g, n, ids) for (g, n), ids in by_key.items() if len(ids) > 1]
    reserved: dict[str, list[str]] = {}
    for op in ops:
        if op.group in RESERVED:
            reserved.setdefault(op.group, []).append(op.operation_id)
    found.extend((g, "", ids) for g, ids in reserved.items())
    return found
