"""``smpy fix-imports``: move an app off deprecated framework import paths."""

from __future__ import annotations

import difflib
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.updates.import_codemod import load_renames, rewrite_source

_SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox", ".smpy"}
)


def iter_python_files(paths: list[Path]) -> Iterator[Path]:
    """Every ``.py`` file under ``paths``, skipping virtualenvs and build output."""
    for path in paths:
        if path.is_file():
            if path.suffix == ".py":
                yield path
            continue
        for candidate in sorted(path.rglob("*.py")):
            if not _SKIP_DIRS.intersection(candidate.relative_to(path).parts[:-1]):
                yield candidate


def fix_imports(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Files or directories to rewrite. Defaults to the current directory."),
    ] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Write nothing; exit 1 if any file would change.")
    ] = False,
    diff: Annotated[
        bool, typer.Option("--diff", help="Print a unified diff instead of writing.")
    ] = False,
) -> None:
    """Rewrite imports of deprecated framework paths to their new area paths.

    Covers ``import x``, ``from x import y``, ``from pkg import moved_module``,
    attribute chains after a bare ``import x`` and dotted strings such as
    ``mock.patch("x.y")``. Run your formatter afterwards to re-sort imports.
    """
    renames = load_renames()
    changed_files = 0
    manual_total = 0
    for file in iter_python_files(paths or [Path()]):
        original = file.read_text(encoding="utf-8")
        result = rewrite_source(original, renames)
        for note in result.manual:
            typer.echo(f"{file}: manual: {note}", err=True)
        manual_total += len(result.manual)
        if not result.changed:
            continue
        changed_files += 1
        if diff:
            typer.echo(
                "".join(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        result.source.splitlines(keepends=True),
                        fromfile=str(file),
                        tofile=str(file),
                    )
                ),
                nl=False,
            )
        elif not check:
            file.write_text(result.source, encoding="utf-8")
        typer.echo(f"{file}: {len(result.changes)} rewrite(s)")
    verb = "would change" if (check or diff) else "changed"
    typer.echo(f"{changed_files} file(s) {verb}; {manual_total} need manual review.")
    if check and changed_files:
        raise typer.Exit(1)
