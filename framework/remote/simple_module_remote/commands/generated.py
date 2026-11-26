"""The click command generated for one OpenAPI operation."""

from __future__ import annotations

from typing import Any

import click

from simple_module_remote.commands.runtime import state_of
from simple_module_remote.generate.body import body_field_summary
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
    fields = body_field_summary(op.body_schema, root) if op.body_kind == "json" else []
    if fields:
        listed = ", ".join(
            f"{sanitize(name)}{'*' if required else ''} ({sanitize(kind)})"
            for name, kind, required in fields
        )
        text += f"\n\nBody fields for --set (* required): {listed}"
    if not success_is_json(op, root):
        text += "\n\nThe response is not JSON: redirect stdout or use --out FILE."
    return click.Command(
        op.name,
        params=params,
        callback=callback,
        help=f"{text}\n\n{route}" if text else route,
        short_help=summary or None,
    )
