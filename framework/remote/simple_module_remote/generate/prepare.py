"""Turn click values into the pieces of one HTTP request."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote

import click

from simple_module_remote.generate.body import BodyError, build_json_body, missing_required
from simple_module_remote.generate.operations import Operation
from simple_module_remote.generate.params import param_map

__all__ = ["Prepared", "prepare_request"]

DEFAULT_CONTENT_TYPE = "application/octet-stream"


@dataclass
class Prepared:
    path: str
    params: dict[str, Any]
    json: Any = None
    files: list[tuple[str, tuple[str, Any]]] | None = None
    data: dict[str, str] | None = None
    content: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict)


def _query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple | list):
        return [_query_value(v) for v in value]
    return value


def _split_pairs(items: Any, flag: str) -> list[tuple[str, str]]:
    pairs = []
    for item in items or ():
        key, sep, value = str(item).partition("=")
        if not sep or not key:
            raise click.UsageError(f"{flag}: expected key=value, got {item!r}")
        pairs.append((key, value))
    return pairs


def _json_body(op: Operation, values: dict[str, Any], root: dict, stdin: TextIO) -> Any:
    try:
        body = build_json_body(
            json_arg=values.get("json_arg"),
            file_arg=values.get("file_arg"),
            sets=values.get("sets") or (),
            set_jsons=values.get("set_jsons") or (),
            body_schema=op.body_schema,
            root=root,
            stdin=stdin,
        )
    except BodyError as exc:
        raise click.UsageError(str(exc)) from None
    missing = missing_required(body if isinstance(body, dict) else {}, op.body_schema, root)
    if missing and (body is None or isinstance(body, dict)):
        raise click.UsageError(f"missing required body fields: {', '.join(missing)}")
    return body


def _multipart(values: dict[str, Any], stack: ExitStack, prep: Prepared) -> None:
    files = []
    for field_name, raw in _split_pairs(values.get("uploads"), "--upload"):
        path = raw[1:] if raw.startswith("@") else raw
        try:
            handle = stack.enter_context(Path(path).open("rb"))  # noqa: SIM115
        except OSError as exc:
            raise click.UsageError(
                f"--upload {field_name}: cannot read {path}: {exc.__class__.__name__}"
            ) from None
        files.append((field_name, (Path(path).name, handle)))
    prep.files = files or None
    prep.data = dict(_split_pairs(values.get("sets"), "--set")) or None


def prepare_request(
    op: Operation, values: dict[str, Any], root: dict, stdin: TextIO, stack: ExitStack
) -> Prepared:
    """Build the request; files opened for upload are registered on ``stack``."""
    path, query = op.path, {}
    for dest, param in param_map(op).items():
        value = values.get(dest)
        if param.location == "path":
            path = path.replace("{" + param.name + "}", quote(str(value), safe=""))
        elif value is not None and value != ():
            query[param.name] = _query_value(value)
    prep = Prepared(path=path, params=query)
    if op.body_kind == "json":
        prep.json = _json_body(op, values, root, stdin)
    elif op.body_kind == "multipart":
        _multipart(values, stack, prep)
    elif op.body_kind == "raw" and values.get("body_file"):
        try:
            prep.content = Path(values["body_file"]).read_bytes()
        except OSError as exc:
            raise click.UsageError(f"--body-file: cannot read: {exc.__class__.__name__}") from None
        prep.headers["Content-Type"] = values.get("content_type") or DEFAULT_CONTENT_TYPE
    return prep
