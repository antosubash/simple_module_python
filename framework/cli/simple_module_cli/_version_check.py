"""Warn when ``smpy new`` runs from an older CLI than PyPI's latest (GH #899).

A new app pins every framework package to the running CLI's own version, and
``uvx --from simple_module_cli`` quietly reuses a ``uv tool install``-ed copy, so
an old tool scaffolds an old app without saying so. The check is best effort: a
short timeout, and any failure (offline, PyPI down, bad JSON) skips it.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import typer
from packaging.version import Version

from simple_module_cli.pypi import PYPI_URL, Fetcher, fetch_latest

CLI_DIST = "simple_module_cli"
_TIMEOUT_SECONDS = 3


def _quick_fetcher(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def newer_release(current: str, fetcher: Fetcher | None = None) -> str | None:
    """The latest stable ``simple_module_cli`` on PyPI if it is newer than ``current``."""
    if current == "0.0.0":  # resolve_framework_version()'s placeholder: no dist-info
        return None
    try:
        latest = fetch_latest(CLI_DIST, include_pre=False, fetcher=fetcher or _quick_fetcher)
        if latest is not None and Version(latest) > Version(current):
            return latest
    except (OSError, ValueError):
        # Timeouts and socket errors are OSErrors; bad JSON or versions are ValueErrors.
        return None
    return None


def warn_if_outdated(current: str, fetcher: Fetcher | None = None) -> None:
    latest = newer_release(current, fetcher)
    if latest is None:
        return
    typer.echo(
        f"WARNING: this smpy is {current}, but {CLI_DIST} {latest} is on PyPI "
        f"({PYPI_URL.format(name=CLI_DIST)}). The new app will pin the framework to "
        f"{current}.\n"
        f"  Upgrade the installed tool: uv tool upgrade {CLI_DIST}\n"
        f"  or run the latest once:     uvx --from {CLI_DIST}@latest smpy new ...",
        err=True,
    )
