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
from simple_module_remote.generate.pairs import split_pairs
from simple_module_remote.generate.params import param_map
from simple_module_remote.http.safety import validate_api_path
from simple_module_remote.output.reasons import os_reason
from simple_module_remote.schema.loader import resolve_ref

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


def _empty_body(op: Operation, root: dict) -> dict:
    """``{}`` for a required body whose fields are all optional; an error for any other shape."""
    schema = resolve_ref(root, op.body_schema) if op.body_schema else {}
    kind = schema.get("type")
    if kind == "object" or not schema or (kind is None and "properties" in schema):
        return {}
    raise click.UsageError("this command needs a request body: use --json, --file or --set")


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
    if body is None and op.body_required:
        return _empty_body(op, root)
    return body


def _multipart(
    op: Operation, values: dict[str, Any], root: dict, stack: ExitStack, prep: Prepared
) -> None:
    files = []
    for field_name, raw in split_pairs(values.get("uploads"), "--upload"):
        path = raw[1:] if raw.startswith("@") else raw
        try:
            handle = stack.enter_context(Path(path).open("rb"))  # noqa: SIM115
        except OSError as exc:
            raise click.UsageError(
                f"--upload {field_name}: cannot read {path}: {os_reason(exc)}"
            ) from None
        files.append((field_name, (Path(path).name, handle)))
    prep.files = files or None
    prep.data = dict(split_pairs(values.get("sets"), "--set")) or None
    given = {name for name, _ in files} | set(prep.data or {})
    missing = missing_required(dict.fromkeys(given), op.body_schema, root)
    if missing:
        raise click.UsageError(
            f"missing required form fields: {', '.join(missing)} (use --upload field=path "
            "or --set field=value)"
        )


def prepare_request(
    op: Operation, values: dict[str, Any], root: dict, stdin: TextIO, stack: ExitStack
) -> Prepared:
    """Build the request; files opened for upload are registered on ``stack``."""
    path, query = op.path, {}
    for dest, param in param_map(op).items():
        value = values.get(dest)
        if param.location == "path":
            if not str(value).strip():
                raise click.UsageError(f"path parameter {param.name!r} must not be empty")
            path = path.replace("{" + param.name + "}", quote(str(value), safe=""))
        elif value is not None and value != ():
            query[param.name] = _query_value(value)
    prep = Prepared(path=path, params=query)
    if op.body_kind == "json":
        prep.json = _json_body(op, values, root, stdin)
    elif op.body_kind == "multipart":
        _multipart(op, values, root, stack, prep)
    elif op.body_kind == "raw" and values.get("body_file"):
        try:
            prep.content = Path(values["body_file"]).read_bytes()
        except OSError as exc:
            raise click.UsageError(
                f"--body-file: cannot read {values['body_file']}: {os_reason(exc)}"
            ) from None
        prep.headers["Content-Type"] = values.get("content_type") or DEFAULT_CONTENT_TYPE
    elif op.body_kind == "raw" and op.body_required:
        raise click.UsageError("this command needs a request body: pass --body-file FILE")
    validate_api_path(prep.path)
    return prep
