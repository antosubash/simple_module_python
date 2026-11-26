"""``build_cli``: the root group with generated and built-in commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import httpx

from simple_module_remote.commands.api_cmd import api
from simple_module_remote.commands.auth_cmd import login, logout, whoami
from simple_module_remote.commands.doctor_cmd import doctor
from simple_module_remote.commands.env_cmd import env_group
from simple_module_remote.commands.generated import operation_command
from simple_module_remote.commands.runtime import AppState, CliError, state_of
from simple_module_remote.commands.schema_cmd import schema_group
from simple_module_remote.config.credentials import KeyringBackend
from simple_module_remote.generate.tree import build_groups
from simple_module_remote.schema.loader import load_schema

__all__ = ["build_cli"]

SCHEMA_SOURCES = ("bundled",)
USAGE_EXIT_CODE = 1
LOGIN_COMMAND = "login"


class _RootGroup(click.Group):
    """Reports every usage error with exit code 1."""

    def make_context(self, *args: Any, **kwargs: Any) -> click.Context:
        try:
            return super().make_context(*args, **kwargs)
        except click.UsageError as exc:
            raise self._as_cli_error(exc) from None

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as exc:
            raise self._as_cli_error(exc) from None

    @staticmethod
    def _as_cli_error(exc: click.UsageError) -> CliError:
        if exc.ctx is not None and exc.ctx.command.name == LOGIN_COMMAND:
            # Arguments of `login` may be a token: never echo them back.
            return CliError("invalid use of login: see `login --help`", USAGE_EXIT_CODE)
        return CliError(f"{exc.format_message()} (see --help)", USAGE_EXIT_CODE)


def build_cli(
    name: str,
    schema_path: Path,
    defaults_path: Path | None = None,
    *,
    version: str = "0",
    transport: httpx.BaseTransport | None = None,
    keyring_backend: KeyringBackend | None = None,
) -> click.Group:
    """Assemble the CLI: built-ins, generated groups at top level and again under ``raw``."""
    schema = load_schema(schema_path)
    groups = build_groups(schema, operation_command)
    state = AppState(
        cli=name,
        version=version,
        schema_path=schema_path,
        defaults_path=defaults_path,
        root=schema,
        transport=transport,
        backend=keyring_backend,
    )

    def root_callback(env: str | None, tenant: str | None, schema_source: str) -> None:
        current = state_of(click.get_current_context())
        current.begin(env, tenant)

    root = _RootGroup(
        name,
        callback=root_callback,
        params=[
            click.Option(["--env", "-e", "env"], help="Environment to use."),
            click.Option(["--tenant", "tenant"], help="Tenant to act for."),
            click.Option(
                ["--schema", "schema_source"],
                type=click.Choice(SCHEMA_SOURCES),
                default="bundled",
                help="Command schema source.",
            ),
        ],
        help=f"{name}: command line for the app's REST API.",
    )
    root.context_settings = {"obj": state}
    raw = click.Group("raw", help="Generated commands, mirrored under raw.")
    for builtin in (env_group, login, logout, whoami, doctor, schema_group, api):
        root.add_command(builtin)
    for group in groups:
        root.add_command(group)
        raw.add_command(group)
    root.add_command(raw)
    return root
