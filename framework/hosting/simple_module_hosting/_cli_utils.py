"""Shared helpers for the ``sm`` CLI (colored output, version lookup)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import click


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
