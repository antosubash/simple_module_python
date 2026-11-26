"""``doctor``: check the setup end to end."""

from __future__ import annotations

import click

from simple_module_remote.commands.runtime import AppState, CliError, fetch_whoami, state_of
from simple_module_remote.commands.schema_cmd import schema_info
from simple_module_remote.config.credentials import TOKEN_ENV_SUFFIX, login_hint
from simple_module_remote.config.environments import Environment
from simple_module_remote.config.paths import env_prefix
from simple_module_remote.http.errors import ApiError, UnsafePathError
from simple_module_remote.http.safety import validate_base_url
from simple_module_remote.output.sanitize import sanitize

__all__ = ["doctor"]


class _Report:
    def __init__(self) -> None:
        self.failed = False

    def ok(self, name: str, detail: str = "") -> None:
        click.echo(f"ok    {name}" + (f": {sanitize(detail)}" if detail else ""))

    def fail(self, name: str, detail: str, fix: str) -> None:
        self.failed = True
        click.echo(f"FAIL  {name}: {sanitize(detail)}")
        click.echo(f"      fix: {fix}")


def _select(state: AppState, report: _Report) -> tuple[Environment, bool] | None:
    try:
        env, explicit = state.select()
    except CliError as exc:
        report.fail("environment", exc.message, f"{state.cli} env add <name> --url URL")
        return None
    report.ok("environment", f"{env.name} ({env.url})")
    return env, explicit


def _check_url(state: AppState, env: Environment, report: _Report) -> bool:
    try:
        validate_base_url(env.url)
    except UnsafePathError as exc:
        report.fail("url", str(exc), f"{state.cli} env add {env.name} --url https://...")
        return False
    report.ok("url", "https or loopback")
    return True


def _check_reachable(state: AppState, env: Environment, report: _Report) -> None:
    try:
        with state.client(env, None) as client:
            response = client.request("GET", "/api/_meta/whoami")
        report.ok("reachable", f"server answered HTTP {response.status_code}")
    except ApiError as exc:
        report.fail("reachable", exc.message, "check the URL, your network and VPN")


def _check_identity(state: AppState, env: Environment, explicit: bool, report: _Report) -> None:
    try:
        token = state.token(env, explicit)
    except CliError as exc:
        report.fail("credentials", exc.message, login_hint(state.cli, env, state.tenant(env)))
        return
    from_var = bool(state.environ.get(env_prefix(state.cli) + TOKEN_ENV_SUFFIX))
    report.ok(
        "credentials",
        f"token from {env_prefix(state.cli)}{TOKEN_ENV_SUFFIX}"
        if from_var
        else "present and bound to this origin",
    )
    try:
        with state.client(env, token) as client:
            who = fetch_whoami(client)
    except ApiError as exc:
        report.fail("whoami", exc.message, login_hint(state.cli, env, state.tenant(env)))
        return
    report.ok("whoami", str(who.get("email")))
    wanted = state.tenant(env)
    if wanted is None:
        report.ok("tenant", "no tenant selected")
    elif who.get("tenant_id") == wanted:
        report.ok("tenant", f"token is pinned to {wanted}")
    else:
        report.fail(
            "tenant",
            f"token is pinned to {who.get('tenant_id') or 'no tenant'}, not {wanted}",
            login_hint(state.cli, env, wanted),
        )


@click.command("doctor", help="Check environment, connectivity, credentials and schema.")
@click.pass_context
def doctor(ctx: click.Context) -> None:
    state = state_of(ctx)
    report = _Report()
    chosen = _select(state, report)
    if chosen is not None:
        env, explicit = chosen
        if _check_url(state, env, report):
            _check_reachable(state, env, report)
            _check_identity(state, env, explicit, report)
    report.ok("schema", f"bundled {state.schema_path} (version {schema_info(state.root)})")
    if report.failed:
        ctx.exit(1)
