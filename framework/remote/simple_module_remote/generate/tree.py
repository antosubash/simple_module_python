"""Build the click command tree from the OpenAPI operations."""

from __future__ import annotations

from typing import Any

import click

from simple_module_remote.commands.runtime import CliError, state_of
from simple_module_remote.config.environments import ConfigError
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import (
    Operation,
    cli_operations,
    find_collisions,
    parse_operations,
)
from simple_module_remote.generate.params import click_params_for, returns_list
from simple_module_remote.output.sanitize import sanitize

__all__ = ["TreeError", "build_groups", "session_only_operations"]


class TreeError(Exception):
    """The schema yields commands that cannot be told apart."""


def _command(op: Operation, root: dict) -> click.Command:
    params = click_params_for(op, list_returning=returns_list(op, root))
    for param in params:
        if isinstance(param, click.Option) and param.help:
            param.help = sanitize(param.help)

    def callback(**values: Any) -> None:
        ctx = click.get_current_context()
        state = state_of(ctx)
        env, explicit = state.select()
        run_ctx = state.run_context(env, explicit)
        with state.guard():
            try:
                code = run_operation(run_ctx, op, values)
            except ConfigError as exc:
                raise CliError(str(exc)) from None
        if code:
            ctx.exit(code)

    summary = sanitize(op.summary)
    text = sanitize(op.description) or summary
    return click.Command(
        op.name,
        params=params,
        callback=callback,
        help=f"{text}\n\n{op.method} {op.path}" if text else f"{op.method} {op.path}",
        short_help=summary or None,
    )


def session_only_operations(schema: dict) -> list[Operation]:
    """Operations a personal access token cannot call."""
    return sorted(
        (op for op in parse_operations(schema) if not op.token_capable),
        key=lambda op: (op.path, op.method),
    )


def build_groups(schema: dict) -> list[click.Group]:
    """One group per tag; raises :class:`TreeError` when names collide."""
    ops = cli_operations(parse_operations(schema))
    collisions = find_collisions(ops)
    if collisions:
        detail = "; ".join(
            f"{group} {name}".strip() + f" ({', '.join(ids)})" for group, name, ids in collisions
        )
        raise TreeError(f"command name collisions in the schema: {detail}")
    groups: dict[str, click.Group] = {}
    for op in ops:
        group = groups.setdefault(op.group, click.Group(op.group))
        group.add_command(_command(op, schema))
    return [groups[name] for name in sorted(groups)]
