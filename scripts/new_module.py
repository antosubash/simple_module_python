#!/usr/bin/env python3
"""Scaffold a new module inside this repository.

Usage:
    make new-module name=<module_name>

A thin wrapper: the files come from the same templates ``smpy create-module``
uses (``simple_module_cli.scaffolding.create_module``, in-repo variant), then
the module is wired into ``host/pyproject.toml`` and the root ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from simple_module_cli.case import InvalidScaffoldNameError, validate_scaffold_name
from simple_module_cli.framework_repo import wire_module
from simple_module_cli.pins import resolve_framework_version
from simple_module_cli.scaffolding import create_module

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new module in this repository")
    parser.add_argument("name", help="Module name in snake_case (e.g. 'orders', 'blog_posts')")
    name = parser.parse_args().name

    try:
        validate_scaffold_name(name)
        if "-" in name:
            raise InvalidScaffoldNameError(f"{name!r}: use underscores, not hyphens")
        create_module(
            ROOT / "modules" / name,
            name=name,
            framework_version=resolve_framework_version(),
            framework_repo=True,
        )
    except (InvalidScaffoldNameError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    wire_module(ROOT, name)
    print(f"\nModule '{name}' scaffolded under modules/{name}/.")
    print(
        "Next: edit models.py, then autogenerate (`make migration` hits Multiple heads):\n"
        "  uv run --project host alembic -c host/alembic.ini revision --autogenerate "
        '-m "<msg>" --head <branch_label>@head\n'
        "Set branch_labels on the module's first migration."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
