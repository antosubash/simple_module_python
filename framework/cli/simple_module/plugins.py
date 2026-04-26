"""Plugin discovery for ``sm`` via the ``simple_module.cli_plugins`` group.

Each entry-point's value (``module:attr``) must resolve to a
:class:`typer.Typer` instance. The entry-point name becomes the
subcommand namespace under ``sm`` (e.g. ``sm host gen-pages``).

Failed loads (broken import, wrong type) print one line to stderr and
are skipped — ``sm`` keeps working with whatever else loads.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from importlib.metadata import EntryPoint, entry_points

import typer

__all__ = ["discover_and_mount"]

_GROUP = "simple_module.cli_plugins"


def _iter_plugin_entries() -> Iterator[EntryPoint]:
    """Indirection point for tests to inject fake entry points."""
    yield from entry_points(group=_GROUP)


def discover_and_mount(root: typer.Typer) -> None:
    """Mount every installed plugin under its entry-point name."""
    seen: set[str] = set()
    for entry in _iter_plugin_entries():
        if entry.name in seen:
            print(
                f"[simple-module] duplicate plugin subgroup '{entry.name}' "
                f"from {entry.value!r}; keeping first registration.",
                file=sys.stderr,
            )
            continue
        try:
            plugin_app = entry.load()
        except Exception as exc:
            print(
                f"[simple-module] failed to load plugin '{entry.name}' ({entry.value}): {exc}",
                file=sys.stderr,
            )
            continue
        if not isinstance(plugin_app, typer.Typer):
            print(
                f"[simple-module] plugin '{entry.name}' did not export a "
                f"typer.Typer instance (got {type(plugin_app).__name__}); skipping.",
                file=sys.stderr,
            )
            continue
        root.add_typer(plugin_app, name=entry.name)
        seen.add(entry.name)
