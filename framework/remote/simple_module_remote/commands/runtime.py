"""Shared per-invocation state for the root group and its commands."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import httpx

from simple_module_remote import __version__ as engine_version
from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    KeyringBackend,
    login_hint,
)
from simple_module_remote.config.environments import (
    Config,
    ConfigError,
    Environment,
    load_config,
    select_env,
    validate_tenant,
)
from simple_module_remote.config.resolve import ResolvedToken, resolve_credential
from simple_module_remote.generate.context import RunContext
from simple_module_remote.generate.execute import run_operation
from simple_module_remote.generate.operations import Operation
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import EXIT_USAGE, REDIRECT_MIN, ApiError, UnsafePathError

__all__ = ["SCHEMA_BUNDLED", "WHOAMI_PATH", "AppState", "CliError", "fetch_whoami", "state_of"]

WHOAMI_PATH = "/api/_meta/whoami"
SCHEMA_BUNDLED = "bundled"
WHOAMI_FIELDS = ("id", "email", "auth_kind")


class CliError(click.ClickException):
    """A usage or configuration failure: message to stderr, exit code 1."""

    def __init__(self, message: str, code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = code  # ty: ignore[invalid-attribute-access]


@dataclass
class AppState:
    cli: str
    version: str
    schema_path: Path
    defaults_path: Path | None
    root: dict
    transport: httpx.BaseTransport | None = None
    backend: KeyringBackend | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    flag_env: str | None = None
    flag_tenant: str | None = None
    _store: CredentialStore | None = None
    _tokens: dict[tuple[str, str | None, str], ResolvedToken] = field(default_factory=dict)

    @property
    def user_agent(self) -> str:
        return f"{self.cli}/{self.version} simple_module_remote/{engine_version}"

    def begin(self, env: str | None, tenant: str | None) -> None:
        """Start an invocation: set the root flags and forget tokens from earlier ones."""
        if tenant is not None:
            with self.guard():
                validate_tenant(tenant)
        self.flag_env = env
        self.flag_tenant = tenant
        self._tokens.clear()

    @contextmanager
    def guard(self) -> Generator[None]:
        """Turn configuration and credential failures into exit-code-1 errors."""
        try:
            yield
        except (ConfigError, CredentialError, UnsafePathError) as exc:
            raise CliError(str(exc)) from None

    def config(self) -> Config:
        with self.guard():
            return load_config(self.cli, self.defaults_path)

    def select(self) -> tuple[Environment, bool]:
        config = self.config()
        try:
            return select_env(config, self.flag_env, self.environ, self.cli)
        except ConfigError as exc:
            hint = ""
            if not config.envs:
                hint = (
                    f"\nno environments are configured yet: `{self.cli} env add <name> --url URL`, "
                    f"`{self.cli} env use <name>`, then `{self.cli} login --token`"
                )
            raise CliError(f"{exc}{hint}") from None

    def tenant(self, env: Environment) -> str | None:
        return self.flag_tenant or env.tenant

    def store(self) -> CredentialStore:
        if self._store is None:
            with self.guard():
                self._store = CredentialStore(self.cli, backend=self.backend)
        return self._store

    def _resolved(self, env: Environment, explicit: bool) -> ResolvedToken:
        key = (env.name, self.tenant(env), env.origin)
        if key not in self._tokens:
            with self.guard():
                self._tokens[key] = resolve_credential(
                    self.store(), env, self.tenant(env), self.environ, self.cli, explicit
                )
        return self._tokens[key]

    def token(self, env: Environment, explicit: bool) -> str:
        return self._resolved(env, explicit).token

    def client(self, env: Environment, token: str | None) -> ApiClient:
        with self.guard():
            return ApiClient(
                env,
                token,
                user_agent=self.user_agent,
                transport=self.transport,
                on_wait=lambda delay: click.echo(
                    f"rate limited (HTTP 429): waiting {delay:g}s before retrying", err=True
                ),
            )

    def run_context(self, env: Environment, explicit: bool) -> RunContext:
        def make_client() -> ApiClient:
            resolved = self._resolved(env, explicit)
            client = self.client(env, resolved.token)
            run_ctx.tenant = resolved.tenant_label  # one canonical name
            return client

        run_ctx = RunContext(
            env=env,
            client_factory=make_client,
            is_tty=sys.stdout.isatty(),
            interactive=sys.stdin.isatty() and sys.stderr.isatty(),
            login_hint=login_hint(self.cli, env, self.tenant(env)),
            tenant=self.tenant(env),
            stdout=sys.stdout,
            stderr=sys.stderr,
            stdin=sys.stdin,
            prompt=lambda text: click.prompt(text, default="", show_default=False, err=True),
            root=self.root,
        )
        return run_ctx

    def run(self, op: Operation, values: dict[str, Any]) -> int:
        """Select the environment and execute ``op``; returns the process exit code."""
        env, explicit = self.select()
        run_ctx = self.run_context(env, explicit)
        with self.guard():
            return run_operation(run_ctx, op, values)


def state_of(ctx: click.Context) -> AppState:
    state = ctx.find_root().obj
    assert isinstance(state, AppState)
    return state


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_identity(data: dict) -> bool:
    if not {"scopes", "tenant_id", "roles"} <= data.keys():
        return False
    optional_text = data["tenant_id"] is None or isinstance(data["tenant_id"], str)
    scopes = data.get("scopes")
    return (
        all(isinstance(data.get(field), str) for field in WHOAMI_FIELDS)
        and optional_text
        and (scopes is None or _strings(scopes))
        and _strings(data["roles"])
    )


def fetch_whoami(client: ApiClient) -> dict:
    """``GET /api/_meta/whoami``; raises :class:`ApiError` on any non-2xx or non-JSON reply."""
    response = client.request("GET", WHOAMI_PATH, follow=False)
    if response.status_code >= REDIRECT_MIN:
        raise ApiError(response.status_code)
    try:
        data = response.json()
    except ValueError:
        raise ApiError(response.status_code, message="whoami response is not JSON") from None
    if not isinstance(data, dict):
        raise ApiError(response.status_code, message="whoami response is not an object")
    if not _is_identity(data):
        raise ApiError(response.status_code, message="whoami response is not an identity document")
    return data
