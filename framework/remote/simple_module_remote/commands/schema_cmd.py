"""``schema status`` and ``schema sync``."""

from __future__ import annotations

import hashlib
import json

import click

from simple_module_remote.commands.generated import operation_command
from simple_module_remote.commands.runtime import SCHEMA_LIVE, AppState, CliError, state_of
from simple_module_remote.config.environments import Environment, validate_env_name
from simple_module_remote.generate.tree import TreeError, build_groups
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import AUTH_STATUSES, ApiError, exit_code_for
from simple_module_remote.schema.cache import (
    CacheMeta,
    SchemaCacheError,
    load_cached,
    parse_schema,
    touch_cache,
    write_cache,
)

__all__ = ["format_age", "schema_fingerprint", "schema_group", "schema_info"]

FINGERPRINT_CHARS = 12
OPENAPI_PATH = "/api/_meta/openapi"
OPENAPI_PERMISSION = "host.openapi.read"
MAX_SCHEMA_BYTES = 32 * 1024 * 1024
MAX_ETAG_CHARS = 256
HTTP_OK = 200
HTTP_NOT_MODIFIED = 304
HTTP_NOT_FOUND = 404
_UNITS = ((86400, "d"), (3600, "h"), (60, "m"))


def schema_fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:FINGERPRINT_CHARS]


def schema_info(root: dict) -> str:
    info = root.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    return str(version) if version else "unknown"


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
    fingerprint = (
        meta.fingerprint[:FINGERPRINT_CHARS]
        if meta is not None
        else schema_fingerprint(state.schema_path.read_bytes())
    )
    click.echo(f"fingerprint: {fingerprint}")
    if state.schema_source == SCHEMA_LIVE and meta is not None:
        click.echo(f"age:         {format_age(meta.age_seconds())} (fetched {meta.fetched_at})")
    elif state.schema_note:
        click.echo(f"live:        {state.schema_note}")


def _safe_etag(value: str | None, client: ApiClient) -> str | None:
    if value is None or len(value) > MAX_ETAG_CHARS or not value.isprintable():
        return None
    return value if client.redact(value) == value else None


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


def _cached_meta(state: AppState, env: Environment) -> CacheMeta | None:
    try:
        cached = load_cached(state.cli, env.name, env.origin)
    except SchemaCacheError:
        return None  # unusable: fetch it again in full
    return cached.meta if cached is not None else None


def _validate(data: bytes, client: ApiClient) -> None:
    """Refuse a body that is too big, not OpenAPI, carries the token, or breaks the tree."""
    if len(data) > MAX_SCHEMA_BYTES:
        raise SchemaCacheError(f"the schema is larger than {MAX_SCHEMA_BYTES} bytes")
    root = parse_schema(data)
    for text in (data.decode("utf-8"), json.dumps(root, ensure_ascii=False)):
        if client.redact(text) != text:
            raise SchemaCacheError("the schema contains the credential; refusing to store it")
    try:
        build_groups(root, operation_command)
    except TreeError as exc:
        raise SchemaCacheError(str(exc)) from None


def _sync(state: AppState, env: Environment, explicit: bool) -> str:
    previous = _cached_meta(state, env)
    headers = {"If-None-Match": previous.etag} if previous and previous.etag else {}
    token = state.token(env, explicit)
    with state.client(env, token) as client:
        try:
            response = client.request("GET", OPENAPI_PATH, headers=headers, follow=False)
        except ApiError as exc:
            raise CliError(f"schema sync failed: {exc.message}", exit_code_for(0)) from None
        if response.status_code == HTTP_NOT_MODIFIED and previous is not None:
            meta = touch_cache(state.cli, env.name, previous)
            return f"unchanged ({meta.fingerprint[:FINGERPRINT_CHARS]})"
        if response.status_code != HTTP_OK:
            raise _refusal(state, env, response.status_code)
        data = response.content
        _validate(data, client)
        etag = _safe_etag(response.headers.get("ETag"), client)
    meta = write_cache(state.cli, env.name, env.origin, data, etag)
    return f"updated ({meta.fingerprint[:FINGERPRINT_CHARS]})"


@schema_group.command("sync", help=f"Fetch and cache the environment's schema ({OPENAPI_PATH}).")
@click.option("--env", "-e", "env_name", help="Environment to sync (default: the root --env).")
@click.pass_context
def sync(ctx: click.Context, env_name: str | None) -> None:
    state = state_of(ctx)
    if env_name is not None:
        with state.guard():
            state.flag_env = validate_env_name(env_name)
    env, explicit = state.select()
    try:
        outcome = _sync(state, env, explicit)
    except SchemaCacheError as exc:
        raise CliError(f"schema sync failed: {exc}") from None
    click.echo(f"schema for {env.name!r} {outcome}; commands for {env.url} now use it")
