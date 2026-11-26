"""``doctor``: check the setup end to end."""

from __future__ import annotations

import click

from simple_module_remote.commands.runtime import (
    SCHEMA_BUNDLED,
    WHOAMI_PATH,
    AppState,
    CliError,
    fetch_whoami,
    state_of,
)
from simple_module_remote.commands.schema_cmd import schema_info
from simple_module_remote.config.credentials import (
    describe_tenant,
    is_single_tenant,
    login_hint,
    tenant_matches,
    token_env_var,
)
from simple_module_remote.config.environments import Environment
from simple_module_remote.config.paths import env_var_name
from simple_module_remote.http.errors import AUTH_STATUSES, ApiError, UnsafePathError
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
        known = sorted(state.config().envs)
        fix = f"{state.cli} env add <name> --url URL"
        if known:
            use = "local" if "local" in known else known[0]
            fix = f"{state.cli} env use {use}  (known: {', '.join(known)}), or {fix}"
        report.fail("environment", exc.message.splitlines()[0], fix)
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
            response = client.request("GET", WHOAMI_PATH)
        shown = "auth required" if response.status_code in AUTH_STATUSES else "ok"
        report.ok(f"reachable ({shown})", f"server answered HTTP {response.status_code}")
    except ApiError as exc:
        report.fail("reachable", exc.message, "check the URL, your network and VPN")


def _check_identity(state: AppState, env: Environment, explicit: bool, report: _Report) -> None:
    wanted = state.tenant(env)
    try:
        token = state.token(env, explicit)
    except CliError as exc:
        var = token_env_var(state.cli)
        if state.environ.get(var) and not explicit:
            fix = (
                f"pass --env {env.name} or set {env_var_name(state.cli)}={env.name} "
                f"so {var} is used"
            )
        elif "chmod" in exc.message:
            fix = exc.message[exc.message.index("run `") + 5 :].split("`")[0]
        else:
            fix = (
                f"create a token at {env.url.rstrip('/')}/api-tokens/, then "
                f"{login_hint(state.cli, env, wanted)} (or --token-stdin)"
            )
        report.fail("credentials", exc.message, fix)
        return
    var = token_env_var(state.cli)
    report.ok(
        "credentials",
        f"token from {var}" if state.environ.get(var) else "present and bound to this origin",
    )
    try:
        with state.client(env, token) as client:
            who = fetch_whoami(client)
    except ApiError as exc:
        fix = (
            "check the URL, your network and VPN"
            if exc.status == 0
            else login_hint(state.cli, env, wanted)
        )
        report.fail("whoami", exc.message, fix)
        return
    report.ok("whoami", str(who.get("email")))
    if wanted is None:
        pinned = who.get("tenant_id")
        report.ok(
            "tenant",
            f"token tenant {describe_tenant(who.get('tenant_slug'), pinned)}"
            if pinned
            else "no tenant selected",
        )
    elif is_single_tenant(who):
        report.ok("tenant", "single-tenant server; --tenant is ignored")
    elif tenant_matches(wanted, who):
        report.ok("tenant", f"token is pinned to {wanted}")
    else:
        report.fail(
            "tenant",
            f"token is pinned to {describe_tenant(who.get('tenant_slug'), who.get('tenant_id'))}, "
            f"not {wanted}",
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
    report.ok("schema", f"{SCHEMA_BUNDLED} {state.schema_path} (version {schema_info(state.root)})")
    if report.failed:
        ctx.exit(1)
