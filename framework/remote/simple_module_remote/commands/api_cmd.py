"""``api METHOD PATH``: call any /api/ endpoint with the same safety rules."""

from __future__ import annotations

from typing import Any

import click

from simple_module_remote.commands.runtime import CliError, state_of
from simple_module_remote.config.environments import ConfigError
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Operation, Param
from simple_module_remote.generate.params import click_params_for, param_map
from simple_module_remote.generate.tree import session_only_operations
from simple_module_remote.http.errors import UnsafePathError
from simple_module_remote.http.safety import validate_api_path

__all__ = ["api"]

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _synthetic(method: str, path: str, queries: list[tuple[str, str]]) -> Operation:
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
        safe=False,
        confirm=False,
        token_capable=True,
    )


def _split_queries(items: tuple[str, ...]) -> list[tuple[str, str]]:
    pairs = []
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise click.UsageError(f"--query: expected key=value, got {item!r}")
        pairs.append((key, value))
    return pairs


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
    queries = _split_queries(values.pop("queries"))
    op = _synthetic(method, path, queries)
    for dest, param in param_map(op).items():
        found = [v for k, v in queries if k == param.name]
        values[dest] = tuple(found) if len(found) > 1 else found[0]
    env, explicit = state.select()
    run_ctx = state.run_context(env, explicit)
    with state.guard():
        try:
            code = run_operation(run_ctx, op, values)
        except ConfigError as exc:
            raise CliError(str(exc)) from None
    if code:
        ctx.exit(code)


api = click.Command(
    "api",
    params=_options(),
    callback=_callback,
    help="Call any /api/ endpoint: api METHOD PATH [--json ... | --set k=v] [--query k=v].",
)
