"""The click command generated for one OpenAPI operation."""

from __future__ import annotations

from typing import Any

import click

from simple_module_remote.commands.runtime import state_of
from simple_module_remote.generate.body_help import body_field_summary, set_addressable
from simple_module_remote.generate.operations import Operation
from simple_module_remote.generate.pagination import pagination_style
from simple_module_remote.generate.params import (
    click_params_for,
    json_response_schema,
    returns_list,
    success_is_json,
)
from simple_module_remote.output.sanitize import sanitize

__all__ = ["operation_command"]


def _fields_help(op: Operation, root: dict) -> str:
    fields, more = body_field_summary(op.body_schema, root)
    if not fields:
        return ""
    # ascii() shows a name exactly where sanitize would drop control characters from it.
    names = [f.name if f.name.isprintable() else ascii(f.name) for f in fields]
    listed = ", ".join(
        f"{name}{'*' if f.required else ''} ({sanitize(f.kind)})"
        for name, f in zip(names, fields, strict=True)
    )
    text = f"\n\nBody fields for --set (* required): {listed}"
    if more:
        text += f", and {more} more (see the schema)"
    if not all(set_addressable(f.name) for f in fields):
        text += ". Empty names and names with . or = cannot be set with --set: use --json or --file"
    return text


def operation_command(op: Operation, root: dict) -> click.Command:
    pageable = (
        returns_list(op, root) and pagination_style(op, json_response_schema(op, root)) is not None
    )
    params = click_params_for(op, list_returning=pageable)
    for param in params:
        if isinstance(param, click.Option) and param.help:
            param.help = sanitize(param.help)

    def callback(**values: Any) -> None:
        ctx = click.get_current_context()
        state = state_of(ctx)
        code = state.run(op, values)
        if code:
            ctx.exit(code)

    route = sanitize(f"{op.method} {op.path}")
    summary = sanitize(op.summary)
    text = sanitize(op.description) or summary
    if op.body_kind == "json":
        text += _fields_help(op, root)
    if not success_is_json(op, root):
        text += "\n\nThe response is not JSON: redirect stdout or use --out FILE."
    return click.Command(
        op.name,
        params=params,
        callback=callback,
        help=f"{text}\n\n{route}" if text else route,
        short_help=summary or None,
    )
