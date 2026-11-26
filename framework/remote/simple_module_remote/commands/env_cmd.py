"""``env`` commands: manage named environments."""

from __future__ import annotations

import click

from simple_module_remote.commands.runtime import CliError, state_of
from simple_module_remote.config.environments import (
    Environment,
    save_config,
    validate_env_name,
)
from simple_module_remote.http.safety import validate_base_url

__all__ = ["env_group"]


def _describe(env: Environment) -> str:
    extras = []
    if env.tenant:
        extras.append(f"tenant={env.tenant}")
    if env.protected:
        extras.append("PROTECTED")
    return f"{env.name}  {env.url}" + (f"  [{', '.join(extras)}]" if extras else "")


@click.group("env", help="Manage named environments.")
def env_group() -> None:
    pass


@env_group.command("list", help="List environments; the current one is marked with *.")
@click.pass_context
def list_envs(ctx: click.Context) -> None:
    config = state_of(ctx).config()
    for name in sorted(config.envs):
        marker = "*" if name == config.current else " "
        click.echo(f"{marker} {_describe(config.envs[name])}")


@env_group.command("add", help="Add or replace an environment.")
@click.argument("name")
@click.option("--url", required=True, help="Base URL of the app, e.g. https://app.example.com.")
@click.option("--tenant", default=None, help="Default tenant for this environment.")
@click.option("--protected/--no-protected", default=False, help="Confirm before mutating calls.")
@click.pass_context
def add_env(ctx: click.Context, name: str, url: str, tenant: str | None, protected: bool) -> None:
    state = state_of(ctx)
    with state.guard():
        validate_env_name(name)
        validate_base_url(url)
    config = state.config()
    config.envs[name] = Environment(name=name, url=url, tenant=tenant, protected=protected)
    config.user_envs.add(name)
    with state.guard():
        save_config(state.cli, config)
    click.echo(f"added environment {name} ({url})")


@env_group.command("use", help="Make an environment the current one.")
@click.argument("name")
@click.pass_context
def use_env(ctx: click.Context, name: str) -> None:
    state = state_of(ctx)
    config = state.config()
    if name not in config.envs:
        raise CliError(f"unknown environment {name!r}: run `{state.cli} env list`")
    config.current = name
    with state.guard():
        save_config(state.cli, config)
    click.echo(f"current environment: {name}")


@env_group.command("remove", help="Remove an environment you added.")
@click.argument("name")
@click.pass_context
def remove_env(ctx: click.Context, name: str) -> None:
    state = state_of(ctx)
    config = state.config()
    if name not in config.user_envs:
        known = (
            "is defined by the project defaults and cannot be removed"
            if (name in config.envs)
            else "does not exist"
        )
        raise CliError(f"environment {name!r} {known}")
    config.user_envs.discard(name)
    config.envs.pop(name, None)
    if config.current == name:
        config.current = None
    with state.guard():
        save_config(state.cli, config)
    click.echo(f"removed environment {name}")


@env_group.command("show", help="Show one environment (default: the current one).")
@click.argument("name", required=False)
@click.pass_context
def show_env(ctx: click.Context, name: str | None) -> None:
    state = state_of(ctx)
    if name is None:
        env, _ = state.select()
    else:
        config = state.config()
        found = config.envs.get(name)
        if found is None:
            raise CliError(f"unknown environment {name!r}: run `{state.cli} env list`")
        env = found
    click.echo(f"name:      {env.name}")
    click.echo(f"url:       {env.url}")
    click.echo(f"tenant:    {env.tenant or '-'}")
    click.echo(f"protected: {'yes' if env.protected else 'no'}")
