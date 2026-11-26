"""``login``, ``logout`` and ``whoami``."""

from __future__ import annotations

import sys

import click

from simple_module_remote.commands.runtime import (
    WHOAMI_PATH,
    AppState,
    CliError,
    fetch_whoami,
    state_of,
)
from simple_module_remote.config.credentials import (
    CredentialError,
    StoredCredential,
    credential_key,
    describe_tenant,
    is_single_tenant,
    login_hint,
    pin_kwargs,
    tenant_matches,
    validate_token,
)
from simple_module_remote.config.environments import save_config
from simple_module_remote.config.resolve import find_credential
from simple_module_remote.http.errors import AUTH_STATUSES, ApiError, exit_code_for
from simple_module_remote.output.sanitize import sanitize

__all__ = ["login", "logout", "whoami"]

MAX_TOKEN_CHARS = 4096
NOT_FOUND = 404


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


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
                "or --token-stdin (--env and --tenant go before the word login)"
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
        raise CliError("choose one of --token and --token-stdin")
    if not (prompt_token or token_stdin):
        raise CliError("browser login arrives in a later release: use --token or --token-stdin")
    env, _ = state.select()
    if token_stdin:
        candidate = sys.stdin.readline(MAX_TOKEN_CHARS + 2).strip()
        if len(candidate) > MAX_TOKEN_CHARS:
            raise CliError(f"the token is longer than {MAX_TOKEN_CHARS} characters")
    else:
        if not _stdin_is_tty():
            raise CliError("stdin is not a terminal: pipe the token to --token-stdin instead")
        candidate = click.prompt("Token", hide_input=True, err=True).strip()
    if not candidate:
        raise CliError("no token provided")
    with state.guard():
        validate_token(candidate, source="the token you entered")
    try:
        with state.client(env, candidate) as client:
            who = fetch_whoami(client)
    except ApiError as exc:
        if exc.status == 0:
            raise _api_failure(
                exc, f"cannot reach {env.name} ({env.url}); nothing was stored"
            ) from None
        if exc.status == NOT_FOUND:
            raise _api_failure(
                exc,
                f"{env.url} has no {WHOAMI_PATH}: check the URL and any path prefix; "
                "nothing was stored",
            ) from None
        raise _api_failure(exc, "the token was not accepted; nothing was stored") from None
    wanted = state.tenant(env)
    single = bool(wanted) and is_single_tenant(who)
    if single:
        click.echo(
            f"note: {env.name} is a single-tenant server; --tenant {sanitize(wanted)} is ignored",
            err=True,
        )
    elif wanted and not tenant_matches(wanted, who):
        raise CliError(
            f"tenant {wanted!r} matches neither the slug nor the id of the token's tenant "
            f"{describe_tenant(who.get('tenant_slug'), who.get('tenant_id'))}; "
            "nothing was stored"
        )
    store = state.store()
    where = credential_key(env.name, None if single else wanted)  # the plain slot when ignored
    with state.guard():
        store.put(
            where,
            StoredCredential(candidate, env.origin, **pin_kwargs(who)),
        )
    if store.using_fallback:
        click.echo("warning: no OS keyring; token stored in a 0600 file", err=True)
    click.echo(f"logged in to {where} as {sanitize(str(who.get('email', 'unknown')))}")
    _adopt_as_current(state, env.name)


def _adopt_as_current(state: AppState, name: str) -> None:
    """With no current environment yet, a configured one just logged in to becomes it (#1241).

    The login itself has already succeeded, so a config that cannot be saved is a
    warning, not a failure.
    """
    try:
        config = state.config()
        if config.current is not None or name not in config.envs:
            return  # a choice already made, or a one-off environment from <CLI>_URL
        config.current = name
        with state.guard():
            save_config(state.cli, config)
    except CliError as exc:
        click.echo(f"warning: {name} was not made the current environment: {exc}", err=True)
        return
    click.echo(f"current environment: {name}", err=True)


@click.command("logout", help="Remove the stored token for the selected environment.")
@click.pass_context
def logout(ctx: click.Context) -> None:
    state = state_of(ctx)
    env, _ = state.select()
    tenant = state.tenant(env)
    where = credential_key(env.name, tenant)
    try:
        found = find_credential(state.store(), env, tenant)
        where = found[0] if found else where
        removed = state.store().delete(where)
    except CredentialError as exc:
        raise CliError(str(exc)) from None
    if not removed:
        raise CliError(f"no stored token for {where}")
    click.echo(f"logged out of {where}")


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
        hint = ""
        if exc.status in AUTH_STATUSES:
            hint = f"\nhint: run `{login_hint(state.cli, env, state.tenant(env))}`"
        raise CliError(f"whoami failed: {exc.message}{hint}", exit_code_for(exc.status)) from None
    if env.protected:
        click.echo("*** PROTECTED ENVIRONMENT ***")
    scopes = who.get("scopes")
    rows = [
        ("user", who.get("email")),
        ("auth", who.get("auth_kind")),
        ("scopes", ", ".join(scopes) if isinstance(scopes, list) else "all"),
        (
            "tenant",
            describe_tenant(who.get("tenant_slug"), who.get("tenant_id"))
            if who.get("tenant_id")
            else "-",
        ),
        ("env", env.name),
        ("url", env.url),
    ]
    for label, value in rows:
        click.echo(f"{label + ':':8}{sanitize(str(value))}")
