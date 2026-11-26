"""The protected-environment confirmation."""

from __future__ import annotations

from collections.abc import Callable

import click

from simple_module_remote.config.environments import Environment

__all__ = ["confirm_protected"]


def confirm_protected(
    env: Environment,
    *,
    mutation: bool,
    op_confirm: bool,
    op_safe: bool,
    yes: bool,
    interactive: bool,
    prompt: Callable[[str], str],
    method: str,
    path: str,
) -> None:
    """Require typing the environment name before a risky call on a protected environment."""
    if not env.protected or not ((mutation and not op_safe) or op_confirm):
        return
    if yes:
        return
    if not interactive:
        raise click.UsageError(
            f"environment {env.name!r} is protected: pass --yes to run {method} {path} "
            "non-interactively"
        )
    answer = prompt(f'Type "{env.name}" to run {method} {path} on {env.name} ({env.url})')
    if answer.rstrip("\r\n") != env.name:  # exact: no other whitespace is forgiven
        raise click.UsageError(f"confirmation did not match {env.name!r}; nothing was sent")
