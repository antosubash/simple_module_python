"""``build_cli``: the root group with generated and built-in commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
import httpx

from simple_module_remote import __version__ as engine_version
from simple_module_remote.commands.api_cmd import api
from simple_module_remote.commands.auth_cmd import login, logout, whoami
from simple_module_remote.commands.doctor_cmd import doctor
from simple_module_remote.commands.env_cmd import env_group
from simple_module_remote.commands.generated import operation_command
from simple_module_remote.commands.runtime import SCHEMA_BUNDLED, AppState, CliError
from simple_module_remote.commands.schema_cmd import schema_group
from simple_module_remote.commands.schema_source import (
    SCHEMA_SOURCES,
    RootFlags,
    SchemaChoice,
    choose_schema,
    peek_root_flags,
)
from simple_module_remote.config.credentials import KeyringBackend
from simple_module_remote.generate.tree import build_groups
from simple_module_remote.schema.loader import load_schema

__all__ = ["build_cli"]

LOGIN_COMMAND = "login"
RAW_GROUP = "raw"
ENV_PARAM = "env"
SCHEMA_PARAM = "schema_source"
BUILTINS = (env_group, login, logout, whoami, doctor, schema_group, api)


class _RootGroup(click.Group):
    """Reports every usage error with exit code 1; installs the generated groups per run."""

    bundled: SchemaChoice
    _generated: tuple[str, ...] = ()

    def install(self, groups: list[click.Group]) -> None:
        """Replace the generated groups (top level and under ``raw``) with ``groups``."""
        for name in self._generated:
            self.commands.pop(name, None)
        raw = click.Group(RAW_GROUP, help="Generated commands, mirrored under raw.")
        for group in groups:
            self.add_command(group)
            raw.add_command(group)
        self.add_command(raw)
        self._generated = (*(g.name for g in groups if g.name), RAW_GROUP)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        state = ctx.obj
        if isinstance(state, AppState):
            flags = self._with_defaults(ctx, peek_root_flags(args))
            choice = choose_schema(
                cli=state.cli,
                defaults_path=state.defaults_path,
                environ=state.environ,
                flags=flags,
                bundled=self.bundled,
                factory=operation_command,
            )
            state.use_schema(choice.source, choice.path, choice.root, choice.meta, choice.note)
            state.preselected = (
                (flags.env, *choice.selected) if choice.selected is not None else None
            )
            self.install(choice.groups)
            builtin = flags.command in {cmd.name for cmd in BUILTINS}
            if choice.error and flags.command is not None and not builtin:
                raise CliError(choice.error)
        return super().parse_args(ctx, args)

    @staticmethod
    def _with_defaults(ctx: click.Context, flags: RootFlags) -> RootFlags:
        """Fill flags absent from the arguments from a wrapper's ``default_map``."""
        defaults = ctx.default_map or {}
        env = flags.env if flags.env is not None else defaults.get(ENV_PARAM)
        schema = flags.schema if flags.schema is not None else defaults.get(SCHEMA_PARAM)
        return RootFlags(
            env if isinstance(env, str) else None,
            schema if isinstance(schema, str) else None,
            flags.command,
        )

    def make_context(self, *args: Any, **kwargs: Any) -> click.Context:
        try:
            return super().make_context(*args, **kwargs)
        except click.exceptions.NoArgsIsHelpError:
            raise  # click's own behaviour: show the help (exit 2 in click 8.2+)
        except click.UsageError as exc:
            raise self._as_cli_error(exc) from None

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.exceptions.NoArgsIsHelpError:
            raise
        except click.UsageError as exc:
            raise self._as_cli_error(exc) from None

    @staticmethod
    def _as_cli_error(exc: click.UsageError) -> CliError:
        if exc.ctx is not None and exc.ctx.command.name == LOGIN_COMMAND:
            # Arguments of `login` may be a token: never echo them back.
            return CliError("invalid use of login: see `login --help`")
        # Only click's own parse errors point at --help; our own refusals are not usage slips.
        hint = " (see --help)" if type(exc) is not click.UsageError else ""
        return CliError(f"{exc.format_message()}{hint}")


def _show_version(
    name: str, version: str
) -> Callable[[click.Context, click.Parameter, bool], None]:
    def callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
        if value and not ctx.resilient_parsing:
            click.echo(f"{name} {version} (simple_module_remote {engine_version})")
            ctx.exit()

    return callback


def build_cli(
    name: str,
    schema_path: Path,
    defaults_path: Path | None = None,
    *,
    version: str = "0",
    transport: httpx.BaseTransport | None = None,
    keyring_backend: KeyringBackend | None = None,
) -> click.Group:
    """Assemble the CLI: built-ins, generated groups at top level and again under ``raw``.

    ``schema_path`` is the bundled schema; each invocation may swap in the selected
    environment's live schema (``schema sync``) before parsing its arguments.
    """
    schema = load_schema(schema_path)
    groups = build_groups(schema, operation_command)
    state = AppState(
        cli=name,
        version=version,
        schema_path=schema_path,
        defaults_path=defaults_path,
        root=schema,
        bundled_root=schema,
        transport=transport,
        backend=keyring_backend,
    )

    root = _RootGroup(
        name,
        callback=state.begin,
        params=[
            click.Option(["--env", "-e", ENV_PARAM], help="Environment to use."),
            click.Option(["--tenant", "tenant"], help="Tenant (slug or id) to act for."),
            click.Option(
                ["--version"],
                is_flag=True,
                is_eager=True,
                expose_value=False,
                callback=_show_version(name, version),
                help="Show the version and exit.",
            ),
            click.Option(
                ["--schema", SCHEMA_PARAM],
                type=click.Choice(SCHEMA_SOURCES),
                expose_value=False,
                help=(
                    "Command schema: live (the environment's schema from `schema sync`) or "
                    "bundled. Default: live when synced for this URL, else bundled."
                ),
            ),
        ],
        help=f"{name}: command line for the app's REST API.",
    )
    root.context_settings = {"obj": state}
    root.bundled = SchemaChoice(SCHEMA_BUNDLED, schema_path, schema, groups)
    for builtin in BUILTINS:
        root.add_command(builtin)
    root.install(groups)
    return root
