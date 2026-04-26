"""Root `sm` command — scaffolders + plugin mount.

This file gets fleshed out in Task 5 (Typer port) and Task 6 (plugin
discovery). For now it exists only so the ``sm = simple_module.cli:main``
console-script entry point resolves cleanly during workspace install.
"""

from __future__ import annotations


def main() -> int:
    raise SystemExit(
        "simple-module CLI is being installed but its commands have not "
        "been wired up yet. Re-install once Task 5 lands."
    )
