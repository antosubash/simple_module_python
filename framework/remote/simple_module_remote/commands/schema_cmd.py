"""``schema status`` and ``schema sync``."""

from __future__ import annotations

import json

import click

from simple_module_remote.commands.runtime import SCHEMA_LIVE, AppState, CliError, state_of
from simple_module_remote.commands.schema_fetch import (
    OPENAPI_PATH,
    fetch_schema,
    replayable_etag,
    vet_schema,
)
from simple_module_remote.config._private_dir import PrivateDir, PrivateDirError
from simple_module_remote.config.environments import Environment, validate_env_name
from simple_module_remote.http.errors import AUTH_STATUSES, ApiError, exit_code_for
from simple_module_remote.output.sanitize import sanitize
from simple_module_remote.schema.cache import (
    LOCK_FILENAME,
    CacheMeta,
    SchemaCacheError,
    load_from,
    open_cache,
    schema_digest,
    touch_in,
    write_to,
)

__all__ = ["format_age", "schema_fingerprint", "schema_group", "schema_info"]

FINGERPRINT_CHARS = 12
MAX_VERSION_CHARS = 64
OPENAPI_PERMISSION = "host.openapi.read"
HTTP_OK = 200
HTTP_NOT_MODIFIED = 304
HTTP_NOT_FOUND = 404
_UNITS = ((86400, "d"), (3600, "h"), (60, "m"))


def schema_fingerprint(root: dict) -> str:
    """Hash of the document's content, not its bytes.

    The same schema exported by ``smpy openapi export`` and served live differs in
    whitespace and key order; both must show the same fingerprint (#1241).
    """
    canonical = json.dumps(root, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return schema_digest(canonical.encode("utf-8"))[:FINGERPRINT_CHARS]


def schema_info(root: dict) -> str:
    info = root.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    return sanitize(str(version))[:MAX_VERSION_CHARS] if version else "unknown"


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    for size, unit in _UNITS:
        if seconds >= size:
            return f"{int(seconds // size)}{unit}"
    return f"{int(seconds)}s"


@click.group("schema", help="Inspect or refresh the command schema.")
def schema_group() -> None:
    pass


@schema_group.command("status", help="Show where the schema comes from, its version and age.")
@click.pass_context
def status(ctx: click.Context) -> None:
    state = state_of(ctx)
    meta = state.schema_meta
    click.echo(f"source:      {state.schema_source}")
    click.echo(f"path:        {state.schema_path}")
    click.echo(f"version:     {schema_info(state.root)}")
    click.echo(f"fingerprint: {schema_fingerprint(state.root)}")
    if state.schema_source == SCHEMA_LIVE and meta is not None:
        click.echo(f"age:         {format_age(meta.age_seconds())} (fetched {meta.fetched_at})")
    elif state.schema_note:
        click.echo(f"live:        {sanitize(state.schema_note)}")


def _refusal(state: AppState, env: Environment, status: int) -> CliError:
    message = f"schema sync failed: HTTP {status}"
    if status in AUTH_STATUSES:
        message += (
            f"\nhint: the token needs the {OPENAPI_PERMISSION} permission; "
            f"check the login with `{state.cli} --env {env.name} whoami`"
        )
    elif status == HTTP_NOT_FOUND:
        message += f"\nhint: this server has no {OPENAPI_PATH} route (an older version?)"
    return CliError(message, code=exit_code_for(status))


def _cached_meta(store: PrivateDir, env: Environment) -> CacheMeta | None:
    try:
        cached = load_from(store, env.name, env.url, env.origin)
    except SchemaCacheError:
        return None  # unusable: fetch it again in full
    return cached.meta if cached is not None else None


def _sync(state: AppState, env: Environment, explicit: bool) -> str:
    token = state.token(env, explicit)
    with open_cache(state.cli, env.name, create=True) as store, store.locked(LOCK_FILENAME):
        previous = _cached_meta(store, env)
        etag = replayable_etag(previous.etag) if previous else None
        headers = {"If-None-Match": etag} if etag else {}
        with state.client(env, token) as client:
            try:
                fetched = fetch_schema(client, headers)
            except ApiError as exc:
                raise CliError(
                    sanitize(f"schema sync failed: {exc.message}"), exit_code_for(0)
                ) from None
            if fetched.status == HTTP_NOT_MODIFIED:
                if previous is None or not etag:
                    raise CliError(
                        "schema sync failed: the server answered 304 Not Modified "
                        "to a request that sent no validator",
                        exit_code_for(0),
                    )
                current = _cached_meta(store, env)
                if current is None or current.fingerprint != previous.fingerprint:
                    raise SchemaCacheError("the cache changed during the sync; run it again")
                touch_in(store, previous)
                cached = load_from(store, env.name, env.url, env.origin)
                shown = schema_fingerprint(cached.root) if cached else previous.fingerprint
                return f"unchanged ({shown[:FINGERPRINT_CHARS]})"
            if fetched.status != HTTP_OK:
                raise _refusal(state, env, fetched.status)
            root = vet_schema(fetched.data, client)
        write_to(store, env.url, env.origin, fetched.data, fetched.etag)
    return f"updated ({schema_fingerprint(root)})"


@schema_group.command("sync", help=f"Fetch and cache the environment's schema ({OPENAPI_PATH}).")
@click.option("--env", "-e", "env_name", help="Environment to sync (default: the root --env).")
@click.pass_context
def sync(ctx: click.Context, env_name: str | None) -> None:
    state = state_of(ctx)
    if env_name is not None:
        if state.flag_env is not None and state.flag_env != env_name:
            raise CliError(
                f"conflicting environments: --env {state.flag_env} before the command and "
                f"--env {env_name} after it; pass one"
            )
        with state.guard():
            state.flag_env = validate_env_name(env_name)
    env, explicit = state.select()
    try:
        outcome = _sync(state, env, explicit)
    except (SchemaCacheError, PrivateDirError) as exc:
        raise CliError(sanitize(f"schema sync failed: {exc}")) from None
    click.echo(f"schema for {env.name!r} {outcome}; commands for {env.url} now use it")
