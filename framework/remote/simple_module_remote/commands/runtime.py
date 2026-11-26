"""Shared per-invocation state for the root group and its commands."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import click
import httpx

from simple_module_remote import __version__ as engine_version
from simple_module_remote.config.credentials import (
    CredentialError,
    CredentialStore,
    KeyringBackend,
    resolve_token,
)
from simple_module_remote.config.environments import (
    Config,
    ConfigError,
    Environment,
    load_config,
    select_env,
)
from simple_module_remote.generate.context import RunContext
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import EXIT_USAGE, ApiError, UnsafePathError

__all__ = ["WHOAMI_PATH", "AppState", "CliError", "fetch_whoami", "state_of"]

WHOAMI_PATH = "/api/_meta/whoami"


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
    _token: str | None = None

    @property
    def user_agent(self) -> str:
        return f"{self.cli}/{self.version} simple_module_remote/{engine_version}"

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
                    f"`{self.cli} env use <name>`, then `{self.cli} login`"
                )
            raise CliError(f"{exc}{hint}") from None

    def tenant(self, env: Environment) -> str | None:
        return self.flag_tenant or env.tenant

    def store(self) -> CredentialStore:
        if self._store is None:
            with self.guard():
                self._store = CredentialStore(self.cli, backend=self.backend)
        return self._store

    def token(self, env: Environment, explicit: bool) -> str:
        if self._token is None:
            with self.guard():
                self._token = resolve_token(
                    self.store(), env, self.tenant(env), self.environ, self.cli, explicit
                )
        return self._token

    def client(self, env: Environment, token: str | None) -> ApiClient:
        with self.guard():
            return ApiClient(env, token, user_agent=self.user_agent, transport=self.transport)

    def run_context(self, env: Environment, explicit: bool) -> RunContext:
        return RunContext(
            env=env,
            client_factory=lambda: self.client(env, self.token(env, explicit)),
            is_tty=sys.stdout.isatty(),
            stdout=sys.stdout,
            stderr=sys.stderr,
            stdin=sys.stdin,
            prompt=lambda text: click.prompt(text, default="", show_default=False, err=True),
            root=self.root,
        )


def state_of(ctx: click.Context) -> AppState:
    state = ctx.find_root().obj
    assert isinstance(state, AppState)
    return state


def fetch_whoami(client: ApiClient) -> dict:
    """``GET /api/_meta/whoami``; raises :class:`ApiError` on any non-2xx or non-JSON reply."""
    response = client.request("GET", WHOAMI_PATH)
    if response.status_code >= 300:
        raise ApiError(response.status_code)
    try:
        data = response.json()
    except ValueError:
        raise ApiError(response.status_code, message="whoami response is not JSON") from None
    if not isinstance(data, dict):
        raise ApiError(response.status_code, message="whoami response is not an object")
    return data
