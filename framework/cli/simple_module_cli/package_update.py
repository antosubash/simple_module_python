"""``smpy package-update`` — bump simple_module_* deps to latest PyPI versions.

Walks the project's ``pyproject.toml`` (and any ``[tool.uv.workspace]`` members),
finds every dependency whose distribution name starts with ``simple_module_`` /
``simple-module-``, queries PyPI for the latest non-yanked release, and points
the constraint at it. Includes optional dependencies and dependency groups.
Matching npm packages use the selected core release when published on npm.

The rewrite preserves the pin style you wrote: ``==0.0.32`` becomes
``==0.0.33``, ``>=0.0.32`` becomes ``>=0.0.33``, and an upper bound that
excludes the latest release skips the dependency instead of being dropped.
``--loosen`` restores the older behaviour of rewriting every constraint to
``name>=<latest>``.

Dependencies whose ``[tool.uv.sources]`` entry points at a workspace member, a
local path, a git ref, or a URL are left untouched — those aren't installed
from PyPI.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import tomlkit
import typer

from simple_module_cli.package_update_deps import (
    Change,
    Skip,
    _collect_sm_deps,
    _process_file,
    _workspace_member_dirs,
    local_sources,
    source_map,
)
from simple_module_cli.package_update_npm import load_manifests, plan_npm
from simple_module_cli.pypi import Fetcher, default_fetcher, fetch_latest

__all__ = ["package_update", "run_update"]


def _print_summary(changes: list[Change], skips: list[Skip], dry_run: bool) -> None:
    if not changes and not skips:
        typer.echo("No simple_module_* or @simple-module-py/* dependencies found.")
        return
    by_file: dict[Path, list[str]] = {}
    for c in changes:
        by_file.setdefault(c.file, []).append(f"  {c.package}: {c.old}  →  {c.new}")
    for s in skips:
        by_file.setdefault(s.file, []).append(f"  {s.package}: skipped ({s.reason})")
    for file, lines in by_file.items():
        typer.echo(f"\n{file}")
        for line in lines:
            typer.echo(line)
    if changes:
        verb = "Would update" if dry_run else "Updated"
        file_count = len({c.file for c in changes})
        typer.echo(f"\n{verb} {len(changes)} dependency(ies) across {file_count} file(s).")
        if not dry_run:
            if any(c.file.suffix == ".toml" for c in changes):
                typer.echo("Run `uv sync` to apply Python changes.")
            for directory in sorted(
                {c.file.parent for c in changes if c.file.name == "package.json"}
            ):
                typer.echo(f"Run `npm install` in {directory} to apply npm changes.")
    elif skips:
        typer.echo("\nNo updates applied.")


def run_update(
    path: Path,
    *,
    dry_run: bool = False,
    include_pre: bool = False,
    loosen: bool = False,
    fetcher: Fetcher | None = None,
) -> None:
    """Programmatic entry point — separated from the Typer command for testing."""
    path = path.resolve()
    root = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    if not root.is_file():
        typer.echo(f"ERROR: {root} not found.", err=True)
        raise typer.Exit(code=1)

    fetch = fetcher or default_fetcher
    root_doc = tomlkit.parse(root.read_text(encoding="utf-8"))
    files: list[tuple[Path, tomlkit.TOMLDocument]] = [(root, root_doc)]
    for member in _workspace_member_dirs(root, root_doc):
        if member == root:
            continue
        files.append((member, tomlkit.parse(member.read_text(encoding="utf-8"))))

    npm_manifests = load_manifests([file.parent for file, _ in files])
    inherited = source_map(root_doc)
    locals_by_file = {file: local_sources(doc, inherited) for file, doc in files}

    # Pre-fetch all unique sm packages in parallel — PyPI calls dominate runtime.
    names = {n for file, doc in files for n in _collect_sm_deps(doc, locals_by_file[file])}
    if any(manifest.packages for manifest in npm_manifests):
        names.add("simple_module_core")
    unique_names = sorted(names)
    cache: dict[str, str | None] = {}
    if unique_names:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_names))) as pool:
            results = pool.map(
                lambda n: (n, fetch_latest(n, include_pre=include_pre, fetcher=fetch)),
                unique_names,
            )
            cache = dict(results)

    all_changes: list[Change] = []
    all_skips: list[Skip] = []
    pending: list[tuple[Path, str]] = []

    for file, doc in files:
        changes, skips, new_doc = _process_file(
            file, doc, cache=cache, loosen=loosen, local=locals_by_file[file]
        )
        all_changes.extend(changes)
        all_skips.extend(skips)
        if new_doc is not None:
            pending.append((file, tomlkit.dumps(new_doc)))

    changes, skips, npm_pending = plan_npm(npm_manifests, cache.get("simple_module_core"), fetch)
    all_changes.extend(changes)
    all_skips.extend(skips)
    pending.extend(npm_pending)

    if not dry_run:
        for file, content in pending:
            file.write_text(content, encoding="utf-8")

    _print_summary(all_changes, all_skips, dry_run)


def package_update(
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show planned changes without writing."),
    ] = False,
    include_pre: Annotated[
        bool,
        typer.Option("--include-pre", help="Include pre-release versions."),
    ] = False,
    loosen: Annotated[
        bool,
        typer.Option(
            "--loosen",
            help="Rewrite Python constraints to `>=<latest>` instead of keeping their operator.",
        ),
    ] = False,
) -> None:
    """Update simple_module_* dependencies and lockstep @simple-module-py/* pins.

    Each constraint keeps the operator it already has — `==0.0.32` becomes
    `==0.0.33`, `>=0.0.32` becomes `>=0.0.33` — so bumping versions never
    silently changes a project's pinning policy. A dependency whose upper
    bound excludes the latest release is reported and left alone. Pass
    `--loosen` to rewrite Python constraints to `>=<latest>` instead.
    npm pins keep exact, caret or tilde style and skip unpublished core versions.
    """
    run_update(path, dry_run=dry_run, include_pre=include_pre, loosen=loosen)
