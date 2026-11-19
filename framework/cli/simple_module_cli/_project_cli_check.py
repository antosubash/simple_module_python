"""Notice when ``smpy`` is not the CLI of the app it runs in (GH #929).

``uv run smpy`` falls through to whatever ``smpy`` is on ``PATH`` once the
project venv lost ``simple_module_cli`` (a plain ``uv sync`` used to drop it).
That is often an older ``uv tool install``-ed copy, which then scaffolds modules
pinned to its own version inside a newer app, or fails with errors that make no
sense inside the project. Reading the app's pins is cheap and local.
"""

from __future__ import annotations

import re
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import typer

from simple_module_cli.pins import PLACEHOLDER_VERSION

_FRAMEWORK_PIN = re.compile(r"^\s*simple[-_]module[-_][a-z0-9_-]+\s*==\s*([^\s;,\[]+)", re.I)

# Commands that legitimately run a CLI of another version than the app's:
# `new` makes an app, `update`/`package-update` change its pins.
_EXEMPT_COMMANDS = frozenset({"new", "update", "package-update"})


def _requirements(doc: dict) -> Iterator[str]:
    project = doc.get("project", {})
    yield from project.get("dependencies", [])
    for extra in project.get("optional-dependencies", {}).values():
        yield from extra
    for group in doc.get("dependency-groups", {}).values():
        yield from group


def _pinned_version(pyproject: Path) -> str | None:
    try:
        doc = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    for requirement in _requirements(doc):
        match = _FRAMEWORK_PIN.match(requirement) if isinstance(requirement, str) else None
        if match:
            return match.group(1)
    return None


def app_framework_pin(start: Path) -> tuple[Path, str] | None:
    """``(project root, version)`` of the nearest project pinning the framework with ``==``.

    A ``smpy new`` app pins every ``simple_module_*`` package to one version, in
    the root ``pyproject.toml`` and (workspace mode) ``host/pyproject.toml``.
    Range requirements, such as this repository's own, are not pins.
    """
    current = start.resolve()
    for candidate in (current, *current.parents):
        for pyproject in (candidate / "pyproject.toml", candidate / "host" / "pyproject.toml"):
            version = _pinned_version(pyproject) if pyproject.is_file() else None
            if version is not None:
                return candidate, version
    return None


def running_cli() -> str:
    """Where the running ``smpy`` lives, for messages."""
    return str(Path(sys.argv[0]).resolve()) if sys.argv and sys.argv[0] else sys.executable


def warn_if_not_the_apps_cli(command: str | None, current: str, start: Path) -> None:
    """One stderr warning when the project pins another framework version than this CLI's."""
    if command in _EXEMPT_COMMANDS or current == PLACEHOLDER_VERSION:
        return
    found = app_framework_pin(start)
    if found is None or found[1] == current:
        return
    root, pinned = found
    typer.echo(
        f"WARNING: this project ({root}) pins the framework to {pinned}, but this smpy is "
        f"{current} ({running_cli()}).\n"
        "  Use the project's own CLI: `uv sync --all-packages`, then `uv run smpy ...`.",
        err=True,
    )
