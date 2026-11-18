"""Plan source-aware Python and npm pin updates; keep the deprecated CLI alias.

Manifest planning is separate from installation so dry runs and tests need no
package manager. The command surface and installation flow live in update_cmd.
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
    collect_sm_deps,
    is_framework_package,
    local_sources,
    normalize,
    process_file,
    source_map,
    workspace_member_dirs,
)
from simple_module_cli.package_update_git import plan_git
from simple_module_cli.package_update_npm import load_manifests, plan_npm
from simple_module_cli.pypi import Fetcher, default_fetcher, fetch_latest

__all__ = ["package_update", "run_update"]


_CORE = "simple-module-core"


def _npm_target(cache: dict[str, str | None], skips: list[Skip]) -> tuple[str | None, str | None]:
    """The core version npm pins follow, or why there is none.

    npm pins move in lockstep with the Python core pin, so when this run left
    that pin alone (an upper bound, a local source) the npm pins stay too.
    """
    for skip in skips:
        if normalize(skip.package) == _CORE:
            return None, f"simple_module_core not updated ({skip.reason})"
    latest = next((v for n, v in cache.items() if normalize(n) == _CORE), None)
    return latest, None if latest else "simple_module_core has no eligible release on PyPI"


def _print_summary(changes: list[Change], skips: list[Skip], dry_run: bool) -> None:
    if not changes and not skips:
        typer.echo("No manifest changes.")
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
    elif skips:
        typer.echo("\nNo updates applied.")


def run_update(
    path: Path,
    *,
    dry_run: bool = False,
    include_pre: bool = False,
    loosen: bool = False,
    fetcher: Fetcher | None = None,
    only: str | None = None,
    git_runner=None,
) -> list[str]:
    """Programmatic entry point — separated from the Typer command for testing."""
    path = path.resolve()
    root = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    if not root.is_file():
        typer.echo(f"ERROR: {root} not found.", err=True)
        raise typer.Exit(code=1)

    fetch = fetcher or default_fetcher
    root_doc = tomlkit.parse(root.read_bytes().decode("utf-8"))
    files: list[tuple[Path, tomlkit.TOMLDocument]] = [(root, root_doc)]
    for member in workspace_member_dirs(root, root_doc):
        if member == root:
            continue
        files.append((member, tomlkit.parse(member.read_bytes().decode("utf-8"))))

    if only and not any(
        normalize(only) == normalize(name)
        for _, doc in files
        for name in collect_sm_deps(doc, set(), only)
    ):
        typer.echo(f"ERROR: {only} is not a dependency of this app.", err=True)
        raise typer.Exit(1)

    git_changes, relock, git_targets = plan_git(files, only=only, git_runner=git_runner)

    npm_manifests = load_manifests([file.parent for file, _ in files])
    inherited = source_map(root_doc)
    effective_sources = {file: {**inherited, **source_map(doc)} for file, doc in files}
    locals_by_file = {file: local_sources(doc, inherited) for file, doc in files}

    # Pre-fetch all unique sm packages in parallel — PyPI calls dominate runtime.
    names = {n for file, doc in files for n in collect_sm_deps(doc, locals_by_file[file], only)}
    if (
        not only
        and not any(_CORE in local for local in locals_by_file.values())
        and any(manifest.packages for manifest in npm_manifests)
        and not any(normalize(n) == _CORE for n in names)
    ):
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

    all_changes: list[Change] = list(git_changes)
    all_skips: list[Skip] = []
    pending: list[tuple[Path, str]] = []

    for file, doc in files:
        changes, skips, new_doc = process_file(
            file, doc, cache=cache, loosen=loosen, local=locals_by_file[file], only=only
        )
        all_changes.extend(changes)
        all_skips.extend(skips)
        if new_doc is not None or any(c.file == file for c in git_changes):
            pending.append((file, tomlkit.dumps(doc)))

    if (
        only
        and is_framework_package(only)
        and any(normalize(name) == normalize(only) for name in names)
        and any(s.reason != "workspace/local source" for s in all_skips)
    ):
        _print_summary([], all_skips, dry_run)
        typer.echo(
            "ERROR: Cannot partially update the framework cohort; resolve skipped PyPI pins first.",
            err=True,
        )
        raise typer.Exit(1)

    all_skips = [
        s
        for s in all_skips
        if not (
            normalize(s.package) in {*git_targets, *relock}
            and isinstance(source := effective_sources[s.file].get(normalize(s.package)), dict)
            and "git" in source
        )
    ]
    target, blocked = _npm_target(cache, all_skips)
    core_sources = [
        effective_sources[file].get(_CORE, {})
        for file, doc in files
        if any(normalize(name) == _CORE for name in collect_sm_deps(doc, set()))
    ]
    if (
        _CORE in git_targets
        and core_sources
        and all(isinstance(s, dict) and "git" in s and "tag" in s for s in core_sources)
        and not any(normalize(s.package) == _CORE for s in all_skips)
    ):
        versions = {str(s["tag"]).removeprefix("v") for s in core_sources}
        if len(versions) == 1:
            target, blocked = versions.pop(), None
    if only and not is_framework_package(only) and _CORE not in git_targets:
        npm_manifests = []
    changes, skips, npm_pending = plan_npm(npm_manifests, target, fetch, blocked=blocked)
    all_changes.extend(changes)
    all_skips.extend(skips)
    pending.extend(npm_pending)

    if not dry_run:
        for file, content in pending:
            # newline="" keeps each file's own line endings (CRLF must not become CRCRLF).
            file.write_text(content, encoding="utf-8", newline="")

    _print_summary(all_changes, all_skips, dry_run)
    return relock


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
    """Deprecated alias for update (removed in 0.0.50)."""
    from simple_module_cli.update_cmd import run_update as update

    try:
        from simple_module_core.deprecation import deprecate
    except ImportError:
        import warnings

        warnings.warn(
            "smpy package-update is deprecated; removed in 0.0.50; use uv run smpy update",
            DeprecationWarning,
            stacklevel=2,
        )
    else:
        deprecate("smpy package-update", remove_in="0.0.50", use="uv run smpy update").warn()
    typer.echo(
        "Deprecated: use `uv run smpy update` (package-update is removed in 0.0.50).", err=True
    )
    update(path, dry_run=dry_run, include_pre=include_pre, loosen=loosen)
