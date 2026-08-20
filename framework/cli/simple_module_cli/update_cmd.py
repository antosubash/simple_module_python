"""``smpy update`` — move git-sourced modules to their newest release tag.

Git-sourced modules pinned to a tag are updated group-wise: every module
sourced from the same repo URL moves to the same new tag (one repo, one
ref — see the git-module-sources spec §3). The new tag must be a ``v*``
semver tag satisfying every sibling's declared dependency range.
Branch-pinned sources re-lock to the newest SHA (dev-mode). Rev-pinned
sources are left alone. A plain PyPI dependency named via ``NAME``
delegates to ``uv lock --upgrade-package``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.add_cmd import ExecRunner, _default_exec_runner, post_install
from simple_module_cli.git_source import (
    derive_range,
    list_remote_refs,
    pick_latest_tag,
    version_tuple,
)
from simple_module_cli.pyproject_edit import (
    dep_constraint,
    git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
)

__all__ = ["run_sources_update", "update_modules"]


def _groups(sources: dict[str, dict]) -> dict[str, list[str]]:
    by_url: dict[str, list[str]] = {}
    for name, src in sources.items():
        by_url.setdefault(str(src["git"]), []).append(name)
    return by_url


def _older_tag(a: str, b: str) -> str:
    """The lower of two v-prefixed tags — every sibling must accept the shared tag."""
    return a if version_tuple(a[1:]) <= version_tuple(b[1:]) else b


def run_sources_update(
    pyproject: Path,
    *,
    only: str | None,
    dry_run: bool,
    git_runner=None,
    exec_runner: ExecRunner | None = None,
) -> None:
    if not pyproject.is_file():
        typer.echo(f"ERROR: {pyproject} not found.", err=True)
        raise typer.Exit(code=1)
    exec_runner = exec_runner or _default_exec_runner
    git_kwargs = {"run": git_runner} if git_runner else {}
    doc = load_pyproject(pyproject)
    sources = git_sources(doc)

    if only and only not in sources:
        # PyPI-sourced (or path-sourced) name: delegate to uv's resolver.
        if dep_constraint(doc, only) is None:
            typer.echo(f"ERROR: {only} is not a dependency of this host.", err=True)
            raise typer.Exit(code=1)
        if dry_run:
            typer.echo(f"Would run: uv lock --upgrade-package {only}")
            return
        exec_runner(["uv", "lock", "--upgrade-package", only], pyproject.parent)
        post_install(pyproject.parent, [], [], exec_runner)
        return

    changed: list[str] = []
    relock: list[str] = []
    for url, names in _groups(sources).items():
        if only and only not in names:
            continue
        tag_pinned = [n for n in names if "tag" in sources[n]]
        branch_pinned = [n for n in names if "branch" in sources[n]]
        for name in branch_pinned:
            typer.echo(f"{name}: tracks branch {sources[name]['branch']!r} — dev-mode re-lock.")
            relock.append(name)
        if not tag_pinned:
            continue
        tags, _ = list_remote_refs(url, **git_kwargs)
        candidate: str | None = None
        for name in tag_pinned:
            best = pick_latest_tag(tags, dep_constraint(doc, name))
            if best is None:
                continue
            candidate = best if candidate is None else _older_tag(candidate, best)
        if candidate is None:
            continue
        current = {str(sources[n]["tag"]) for n in tag_pinned}
        if current == {candidate}:
            typer.echo(f"{url}: up to date ({candidate}).")
            continue
        version = candidate[1:]
        uv_sources = doc["tool"]["uv"]["sources"]  # exists: git_sources() was non-empty
        for name in tag_pinned:
            uv_sources[name]["tag"] = candidate
            write_dependency(doc, name, derive_range(version))
            changed.append(name)
            typer.echo(f"{name}: → {candidate}")

    if not changed and not relock:
        if not sources:
            typer.echo("No git-sourced modules found. For PyPI deps use `smpy package-update`.")
        return
    if dry_run:
        typer.echo("(dry-run) no files written.")
        return
    if changed:
        save_pyproject(pyproject, doc)
    for name in relock:
        exec_runner(["uv", "lock", "--upgrade-package", name], pyproject.parent)
    post_install(pyproject.parent, changed, [], exec_runner)


def update_modules(
    name: Annotated[
        str | None,
        typer.Argument(help="Module dist name. Omit to update every git-sourced module."),
    ] = None,
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show planned changes without writing.")
    ] = False,
) -> None:
    """Update git-sourced modules to their newest release tag (group-wise per repo)."""
    pyproject = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    run_sources_update(pyproject, only=name, dry_run=dry_run)
