"""Pick the command schema for one invocation: the env's live cache or the bundled file.

The command tree is built from the schema before click parses the arguments, so the
root flags that choose it (``--env``, ``--schema``) are peeked from the raw arguments
first. The peek mirrors click's rules for the root options; click still parses and
validates them afterwards.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import click

from simple_module_remote.commands.runtime import SCHEMA_BUNDLED, SCHEMA_LIVE
from simple_module_remote.config.environments import ConfigError, load_config, select_env
from simple_module_remote.generate.operations import Operation
from simple_module_remote.generate.tree import TreeError, build_groups
from simple_module_remote.schema.cache import CacheMeta, SchemaCacheError, load_cached

__all__ = [
    "SCHEMA_SOURCES",
    "RootFlags",
    "SchemaChoice",
    "choose_schema",
    "peek_root_flags",
]

SCHEMA_SOURCES = (SCHEMA_BUNDLED, SCHEMA_LIVE)
_ENV_OPTS = ("--env", "-e")
_SCHEMA_OPT = "--schema"
_VALUED_OPTS = (*_ENV_OPTS, "--tenant", _SCHEMA_OPT)
_END_OF_OPTIONS = "--"


@dataclass(frozen=True)
class RootFlags:
    env: str | None = None
    schema: str | None = None
    command: str | None = None  # the first subcommand name, if any


def _split(token: str) -> tuple[str, str | None]:
    """``--opt=value`` / ``-evalue`` into ``(opt, value)``; ``(token, None)`` otherwise."""
    if token.startswith("--") and "=" in token:
        name, value = token.split("=", 1)
        return name, value
    if token.startswith("-e") and not token.startswith("--") and len(token) > len("-e"):
        return "-e", token[len("-e") :]
    return token, None


def peek_root_flags(args: Sequence[str]) -> RootFlags:
    values: dict[str, str] = {}
    rest = list(args)
    while rest:
        token = rest.pop(0)
        if token == _END_OF_OPTIONS:
            return RootFlags(values.get("env"), values.get("schema"), rest[0] if rest else None)
        if not token.startswith("-") or token == "-":
            return RootFlags(values.get("env"), values.get("schema"), token)
        name, value = _split(token)
        if name not in _VALUED_OPTS:
            continue  # a root flag (--version, --help) or an error click reports itself
        if value is None:
            if not rest:
                break
            value = rest.pop(0)
        if name in _ENV_OPTS:
            values["env"] = value
        elif name == _SCHEMA_OPT:
            values["schema"] = value
    return RootFlags(values.get("env"), values.get("schema"), None)


@dataclass
class SchemaChoice:
    source: str
    path: Path
    root: dict
    groups: list[click.Group]
    env: str | None = None
    meta: CacheMeta | None = None
    # Why the live schema is not in use (shown by `schema status`); empty when it is.
    note: str = ""
    # Set when `--schema live` was asked for but cannot be honoured.
    error: str | None = None


Factory = Callable[[Operation, dict], click.Command]


def choose_schema(
    *,
    cli: str,
    defaults_path: Path | None,
    environ: Mapping[str, str],
    flags: RootFlags,
    bundled: SchemaChoice,
    factory: Factory,
) -> SchemaChoice:
    """The live cache for the selected env when it is usable, else ``bundled``.

    ``--schema bundled`` always yields ``bundled``; ``--schema live`` yields the live
    cache or ``bundled`` carrying an ``error`` the caller raises before running a
    generated command.
    """
    if flags.schema == SCHEMA_BUNDLED:
        return _fallback(bundled, "pinned with --schema bundled", None, None)
    try:
        env, _ = select_env(load_config(cli, defaults_path), flags.env, environ, cli)
    except ConfigError:
        return _fallback(bundled, "no environment selected", None, flags.schema, cli)
    sync = f"`{cli} --env {env.name} schema sync`"
    try:
        cached = load_cached(cli, env.name, env.origin)
        if cached is None:
            raise SchemaCacheError(f"no live schema cached for {env.name!r}")
        groups = build_groups(cached.root, factory)
    except (SchemaCacheError, TreeError) as exc:
        return _fallback(bundled, f"{exc}: run {sync}", env.name, flags.schema, cli)
    return SchemaChoice(SCHEMA_LIVE, cached.path, cached.root, groups, env.name, cached.meta)


def _fallback(
    bundled: SchemaChoice,
    note: str,
    env: str | None,
    requested: str | None,
    cli: str = "",
) -> SchemaChoice:
    error = None
    if requested == SCHEMA_LIVE:
        error = f"--schema live: {note}"
        if env is None:
            error += f" (pass --env, then run `{cli} --env <name> schema sync`)"
    return SchemaChoice(
        SCHEMA_BUNDLED, bundled.path, bundled.root, bundled.groups, env, note=note, error=error
    )
