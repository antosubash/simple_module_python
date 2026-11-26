"""Build the click command tree from the OpenAPI operations."""

from __future__ import annotations

from collections.abc import Callable

import click

from simple_module_remote.generate.operations import (
    Operation,
    cli_operations,
    find_collisions,
    parse_operations,
)

__all__ = ["TreeError", "build_groups", "session_only_operations"]


class TreeError(Exception):
    """The schema yields commands that cannot be told apart."""


def session_only_operations(schema: dict) -> list[Operation]:
    """Operations a personal access token cannot call."""
    return sorted(
        (op for op in parse_operations(schema) if not op.token_capable),
        key=lambda op: (op.path, op.method),
    )


def build_groups(
    schema: dict, factory: Callable[[Operation, dict], click.Command]
) -> list[click.Group]:
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
        group.add_command(factory(op, schema))
    return [groups[name] for name in sorted(groups)]
