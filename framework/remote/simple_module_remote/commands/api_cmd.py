"""``api METHOD PATH``: call any /api/ endpoint with the same safety rules."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

import click

from simple_module_remote.commands.runtime import state_of
from simple_module_remote.generate.operations import Operation, Param, parse_operations
from simple_module_remote.generate.pairs import split_pairs
from simple_module_remote.generate.params import click_params_for, param_map
from simple_module_remote.generate.tree import session_only_operations
from simple_module_remote.http.errors import UnsafePathError
from simple_module_remote.http.safety import validate_api_path

__all__ = ["api"]

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_TEMPLATE_VAR = re.compile(r"\{[^}]+\}")


def _matching(root: dict, method: str, path: str) -> list[Operation]:
    """Schema operations whose path template matches ``path``: they define its risk."""
    found = []
    for op in parse_operations(root):
        pattern = "[^/]+".join(re.escape(part) for part in _TEMPLATE_VAR.split(op.path))
        if op.method == method and re.fullmatch(pattern, path):
            found.append(op)
    return found


def _synthetic(
    method: str, path: str, queries: list[tuple[str, str]], root: dict | None = None
) -> Operation:
    # Risk comes from the endpoint the server will route to: match the decoded path.
    matched = _matching(root, method, unquote(path)) if root else []
    names: dict[str, int] = {}
    for key, _ in queries:
        names[key] = names.get(key, 0) + 1
    params = tuple(
        Param(
            name=key,
            location="query",
            required=False,
            schema={"type": "array"} if count > 1 else {},
            description="",
        )
        for key, count in names.items()
    )
    return Operation(
        operation_id="api",
        method=method,
        path=path,
        group="api",
        name="api",
        params=params,
        body_kind="json" if method in BODY_METHODS else "none",
        body_schema=None,
        summary="",
        description="",
        safe=bool(matched) and all(op.safe for op in matched),
        confirm=any(op.confirm for op in matched),
        token_capable=True,
    )


def _list_session_only(schema: dict) -> None:
    for op in session_only_operations(schema):
        click.echo(f"{op.method} {op.path} {op.operation_id}")


def _options() -> list[click.Parameter]:
    template = _synthetic("POST", "/api/x", [])
    shared = [p for p in click_params_for(template) if p.name in _SHARED]
    return [
        click.Argument(["method"], required=False, metavar="METHOD"),
        click.Argument(["path"], required=False, metavar="PATH"),
        click.Option(["--query", "queries"], multiple=True, help="Query parameter: key=value."),
        click.Option(
            ["--session-only", "session_only"],
            is_flag=True,
            help="List operations a token cannot call, then exit.",
        ),
        *shared,
    ]


_SHARED = frozenset(
    {
        "json_arg",
        "file_arg",
        "sets",
        "set_jsons",
        "dry_run",
        "output",
        "columns",
        "quiet",
        "out",
        "yes",
    }
)


def _callback(**values: Any) -> None:
    ctx = click.get_current_context()
    state = state_of(ctx)
    if values.pop("session_only"):
        _list_session_only(state.root)
        return
    method, path = values.pop("method"), values.pop("path")
    if not method or not path:
        raise click.UsageError("usage: api METHOD PATH (or --session-only)")
    method = method.upper()
    if method not in METHODS:
        raise click.UsageError(f"METHOD must be one of: {', '.join(METHODS)}")
    try:
        validate_api_path(path)
    except UnsafePathError as exc:
        raise click.UsageError(str(exc)) from None
    if method not in BODY_METHODS and any(
        values.get(k) for k in ("json_arg", "file_arg", "sets", "set_jsons")
    ):
        raise click.UsageError(f"{method} takes no request body: drop --json/--file/--set")
    queries = split_pairs(values.pop("queries"), "--query")
    op = _synthetic(method, path, queries, state.root)
    for dest, param in param_map(op).items():
        found = [v for k, v in queries if k == param.name]
        values[dest] = tuple(found) if len(found) > 1 else found[0]
    code = state.run(op, values)
    if code:
        ctx.exit(code)


api = click.Command(
    "api",
    params=_options(),
    callback=_callback,
    help="Call any /api/ endpoint: api METHOD PATH [--json ... | --set k=v] [--query k=v].",
)
