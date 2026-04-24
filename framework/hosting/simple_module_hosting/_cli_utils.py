"""Shared helpers for the ``sm`` CLI (colored output, version lookup)."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, entry_points, version

import click

CLI_ENTRY_POINT_GROUP = "simple_module_cli"
_logger = logging.getLogger(__name__)


def pkg_version() -> str:
    try:
        return version("simple_module_hosting")
    except PackageNotFoundError:
        return "unknown"


def error(msg: str, hint: str | None = None) -> None:
    click.secho(f"ERROR: {msg}", fg="red", err=True)
    if hint:
        click.echo(f"  hint: {hint}", err=True)


def warn(msg: str) -> None:
    click.secho(f"WARNING: {msg}", fg="yellow", err=True)


def info(msg: str) -> None:
    click.secho(f"==> {msg}", fg="cyan")


def attach_plugin_commands(group: click.Group) -> None:
    """Attach every Click command/group declared in the `simple_module_cli` entry-point group.

    Each module can contribute CLI commands by declaring, in its pyproject.toml::

        [project.entry-points.simple_module_cli]
        users = "users.cli:cli"

    The loaded object must be a ``click.BaseCommand`` (command or group); anything
    else is skipped with a warning. Failures to import are logged and skipped so
    a broken plugin never prevents ``sm --help`` from running.
    """
    for ep in entry_points(group=CLI_ENTRY_POINT_GROUP):
        try:
            cmd = ep.load()
        except Exception:
            _logger.exception("Failed to load CLI plugin %r — skipping", ep.name)
            continue
        if not isinstance(cmd, click.Command):
            _logger.warning("CLI plugin %r is not a click command — skipping", ep.name)
            continue
        group.add_command(cmd, name=ep.name)


def print_discovered_modules() -> None:
    """Print a table of modules discovered via the simple_module entry-point group."""
    from simple_module_core import discover_modules
    from simple_module_core.discovery import get_module_package_name

    rows = sorted(
        (m.meta.name, m.meta.version, get_module_package_name(m)) for m in discover_modules()
    )
    if not rows:
        click.secho("No modules discovered.", fg="yellow")
        return
    nw = max(len(r[0]) for r in rows)
    click.secho(f"{'NAME':<{nw}}  VERSION  PACKAGE", bold=True)
    for n, v, p in rows:
        click.echo(f"{n:<{nw}}  {v:<7}  {p}")
