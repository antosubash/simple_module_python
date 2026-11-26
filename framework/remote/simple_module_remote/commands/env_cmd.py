"""``env`` commands: manage named environments."""

from __future__ import annotations

import click

from simple_module_remote.commands.runtime import AppState, CliError, state_of
from simple_module_remote.config.credentials import CredentialDeleteError
from simple_module_remote.config.environments import (
    Config,
    Environment,
    save_config,
    validate_env_name,
    validate_tenant,
)
from simple_module_remote.http.safety import normalize_url, validate_base_url
from simple_module_remote.output.sanitize import sanitize

__all__ = ["env_group"]


def _describe(env: Environment) -> str:
    extras = []
    if env.tenant:
        extras.append(f"tenant={env.tenant}")
    if env.protected:
        extras.append("PROTECTED")
    line = f"{env.name}  {env.url}" + (f"  [{', '.join(extras)}]" if extras else "")
    return sanitize(line)


def _known(state: AppState, config: Config, name: str) -> Environment:
    found = config.envs.get(name)
    if found is None:
        raise CliError(f"unknown environment {name!r}: run `{state.cli} env list`")
    return found


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
@click.option(
    "--url",
    default=None,
    help="Base URL of the app, e.g. https://app.example.com (required for a new environment).",
)
@click.option("--tenant", default=None, help="Default tenant (kept when omitted).")
@click.option(
    "--protected/--no-protected",
    default=None,
    help="Confirm before mutating calls (kept when omitted).",
)
@click.pass_context
def add_env(
    ctx: click.Context, name: str, url: str | None, tenant: str | None, protected: bool | None
) -> None:
    state = state_of(ctx)
    with state.guard():
        validate_env_name(name)
        if url is not None:
            url = normalize_url(validate_base_url(url))
        if tenant:
            validate_tenant(tenant)
    config = state.config()
    existing = config.envs.get(name)
    url_given = url is not None
    if url is None:
        if existing is None:
            raise CliError(f"--url is required to add the new environment {name!r}")
        url = existing.url
    changed = existing is not None and (
        url != existing.url or (tenant is not None and tenant != existing.tenant)
    )
    # Only what was passed changes; the rest comes from the existing (or default) environment.
    overrides = dict(config.overrides.get(name, {}))
    if url_given or existing is None:  # an inherited url stays inherited, not copied
        overrides["url"] = url
    if tenant is not None:
        overrides["tenant"] = tenant
    if protected is not None:
        overrides["protected"] = protected
    config.envs[name] = Environment(
        name=name,
        url=url,
        tenant=tenant if tenant is not None else (existing.tenant if existing else None),
        protected=protected
        if protected is not None
        else (existing.protected if existing else False),
    )
    config.overrides[name] = overrides
    config.user_envs.add(name)
    with state.guard():
        save_config(state.cli, config)
    click.echo(f"{'updated' if existing else 'added'} environment {name} ({sanitize(url)})")
    with state.guard():
        has_login = changed and bool(state.store().keys_for_env(name))
    if has_login:
        click.echo(
            f"warning: the stored login for {name} was issued for the old url/tenant and may "
            f"no longer apply; run `{state.cli} --env {name} login --token-stdin` again",
            err=True,
        )


@env_group.command("use", help="Make an environment the current one.")
@click.argument("name")
@click.pass_context
def use_env(ctx: click.Context, name: str) -> None:
    state = state_of(ctx)
    config = state.config()
    _known(state, config, name)
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
    was_current = config.current == name
    # Tenants the config has seen (before this env is dropped): legacy keyring keys to try.
    tenants = sorted(
        {e.tenant for e in config.envs.values() if e.tenant}
        | ({state.flag_tenant} if state.flag_tenant else set())
    )
    # Logins first: if one cannot be deleted the environment stays, so the removal can be retried.
    with state.guard():
        store = state.store()
    try:
        removed = store.delete_env(name, tenants)
    except CredentialDeleteError as exc:
        for key in exc.removed:
            click.echo(f"removed stored login {key}")
        raise CliError(
            f"{exc}; environment {name!r} was kept: fix the credential store and run "
            f"`{state.cli} env remove {name}` again"
        ) from None
    config.user_envs.discard(name)
    config.overrides.pop(name, None)
    config.envs.pop(name, None)
    if was_current:
        config.current = None
    with state.guard():
        save_config(state.cli, config)
        reset = name in state.config().envs  # a project default of the same name remains
    if reset:
        click.echo(f"reset environment {name} to the project default")
    else:
        click.echo(f"removed environment {name}")
    if not store.using_fallback:
        click.echo(
            "note: the OS keyring cannot be listed, so a login for a tenant this CLI never "
            f"recorded may remain: `{state.cli} --env {name} --tenant T logout` removes one",
            err=True,
        )
    if was_current:
        click.echo("no environment is selected now: run `env use <name>`", err=True)
    for key in removed:
        click.echo(f"removed stored login {key}")


@env_group.command("show", help="Show one environment (default: the current one).")
@click.argument("name", required=False)
@click.pass_context
def show_env(ctx: click.Context, name: str | None) -> None:
    state = state_of(ctx)
    if name is None:
        env, _ = state.select()
    else:
        env = _known(state, state.config(), name)
    click.echo(f"name:      {sanitize(env.name)}")
    click.echo(f"url:       {sanitize(env.url)}")
    click.echo(f"tenant:    {sanitize(env.tenant or '-')}")
    click.echo(f"protected: {'yes' if env.protected else 'no'}")
