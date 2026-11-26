"""``login``, ``logout`` and ``whoami``."""

from __future__ import annotations

import sys

import click

from simple_module_remote.commands.runtime import CliError, fetch_whoami, state_of
from simple_module_remote.config.credentials import (
    CredentialError,
    StoredCredential,
    credential_key,
)
from simple_module_remote.http.errors import ApiError, exit_code_for
from simple_module_remote.output.sanitize import sanitize

__all__ = ["login", "logout", "whoami"]


def _api_failure(exc: ApiError, what: str) -> click.ClickException:
    return CliError(f"{what}: {exc.message}", exit_code_for(exc.status))


class _LoginCommand(click.Command):
    """Never echoes extra arguments: they may be a token typed on the command line."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except click.UsageError:
            raise CliError(
                "login takes no arguments and no token value: use --token (hidden prompt) "
                "or --token-stdin"
            ) from None


@click.command(
    "login", cls=_LoginCommand, help="Store a personal access token for the selected environment."
)
@click.option("--token", "prompt_token", is_flag=True, help="Prompt for the token (hidden input).")
@click.option("--token-stdin", is_flag=True, help="Read the token from one line of stdin.")
@click.pass_context
def login(ctx: click.Context, prompt_token: bool, token_stdin: bool) -> None:
    state = state_of(ctx)
    if prompt_token and token_stdin:
        raise click.UsageError("choose one of --token and --token-stdin")
    if not (prompt_token or token_stdin):
        raise CliError("browser login arrives in a later release: use --token or --token-stdin")
    env, _ = state.select()
    if token_stdin:
        candidate = sys.stdin.readline().strip()
    else:
        candidate = click.prompt("Token", hide_input=True, err=True).strip()
    if not candidate:
        raise CliError("no token provided")
    try:
        with state.client(env, candidate) as client:
            who = fetch_whoami(client)
    except ApiError as exc:
        raise _api_failure(exc, "the token was not accepted; nothing was stored") from None
    wanted = state.tenant(env)
    if wanted and who.get("tenant_id") != wanted:
        pinned = who.get("tenant_id") or "no tenant"
        raise CliError(
            f"tenant {wanted!r} does not match the token's pinned tenant id "
            f"{pinned!r}; nothing was stored"
        )
    store = state.store()
    with state.guard():
        store.put(
            credential_key(env.name, state.tenant(env)), StoredCredential(candidate, env.origin)
        )
    if store.using_fallback:
        click.echo("warning: no OS keyring; token stored in a 0600 file", err=True)
    click.echo(f"logged in to {env.name} as {sanitize(str(who.get('email', 'unknown')))}")


@click.command("logout", help="Remove the stored token for the selected environment.")
@click.pass_context
def logout(ctx: click.Context) -> None:
    state = state_of(ctx)
    env, _ = state.select()
    try:
        removed = state.store().delete(credential_key(env.name, state.tenant(env)))
    except CredentialError as exc:
        raise CliError(str(exc)) from None
    click.echo(f"logged out of {env.name}" if removed else f"no stored token for {env.name}")


@click.command("whoami", help="Show the identity the selected environment sees.")
@click.pass_context
def whoami(ctx: click.Context) -> None:
    state = state_of(ctx)
    env, explicit = state.select()
    token = state.token(env, explicit)
    try:
        with state.client(env, token) as client:
            who = fetch_whoami(client)
    except ApiError as exc:
        raise _api_failure(exc, "whoami failed") from None
    if env.protected:
        click.echo("*** PROTECTED ENVIRONMENT ***")
    scopes = who.get("scopes")
    rows = [
        ("user", who.get("email")),
        ("auth", who.get("auth_kind")),
        ("scopes", ", ".join(scopes) if isinstance(scopes, list) else "all"),
        ("tenant", who.get("tenant_id") or "-"),
        ("env", env.name),
        ("url", env.url),
    ]
    for label, value in rows:
        click.echo(f"{label + ':':8}{sanitize(str(value))}")
