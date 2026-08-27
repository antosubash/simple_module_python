"""``smpy package-update`` — bump simple_module_* deps to latest PyPI versions.

Walks the project's ``pyproject.toml`` (and any ``[tool.uv.workspace]`` members),
finds every dependency whose distribution name starts with ``simple_module_`` /
``simple-module-``, queries PyPI for the latest non-yanked release, and points
the constraint at it.

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

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import tomlkit
import typer
from tomlkit.items import Array, Table

from simple_module_cli.pypi import Fetcher, default_fetcher, fetch_latest
from simple_module_cli.requirements import parse_requirement, rewrite_requirement

__all__ = ["package_update", "run_update"]

_SM_PREFIX_RE = re.compile(r"^simple[_-]module[_-]", re.IGNORECASE)


@dataclass(frozen=True)
class Change:
    file: Path
    package: str
    old: str
    new: str


@dataclass(frozen=True)
class Skip:
    file: Path
    package: str
    reason: str


def _is_sm_package(name: str) -> bool:
    return bool(_SM_PREFIX_RE.match(name))


def _dep_name(spec: str) -> str | None:
    """Extract the distribution name from a PEP 508 requirement string."""
    parsed = parse_requirement(spec)
    return parsed.name if parsed else None


def _is_local_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if source.get("workspace") is True:
        return True
    return any(key in source for key in ("path", "git", "url"))


def _get_uv_section(doc: tomlkit.TOMLDocument, key: str) -> dict[str, Any] | None:
    tool = doc.get("tool")
    if not isinstance(tool, dict):
        return None
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return None
    section = uv.get(key)
    return section if isinstance(section, dict) else None


def _workspace_member_dirs(root_pyproject: Path, doc: tomlkit.TOMLDocument) -> list[Path]:
    workspace = _get_uv_section(doc, "workspace")
    if workspace is None:
        return []
    members = workspace.get("members") or []
    base = root_pyproject.parent
    out: list[Path] = []
    for pattern in members:
        for match in sorted(base.glob(str(pattern))):
            if (match / "pyproject.toml").is_file():
                out.append(match / "pyproject.toml")
    return out


def _local_sources(doc: tomlkit.TOMLDocument) -> set[str]:
    sources = _get_uv_section(doc, "sources")
    if sources is None:
        return set()
    return {name for name, src in sources.items() if _is_local_source(src)}


def _collect_sm_deps(doc: tomlkit.TOMLDocument) -> list[str]:
    """Return distribution names of simple_module_* deps in this doc that aren't local-sourced."""
    project = doc.get("project")
    if not isinstance(project, (dict, Table)):
        return []
    deps = project.get("dependencies")
    if not isinstance(deps, (list, Array)):
        return []
    local = _local_sources(doc)
    out: list[str] = []
    for raw in deps:
        name = _dep_name(str(raw))
        if name and _is_sm_package(name) and name not in local:
            out.append(name)
    return out


def _process_file(
    path: Path,
    doc: tomlkit.TOMLDocument,
    *,
    cache: dict[str, str | None],
    loosen: bool = False,
) -> tuple[list[Change], list[Skip], tomlkit.TOMLDocument | None]:
    project = doc.get("project")
    if not isinstance(project, (dict, Table)):
        return [], [], None
    deps = project.get("dependencies")
    if not isinstance(deps, (list, Array)):
        return [], [], None

    local = _local_sources(doc)
    changes: list[Change] = []
    skips: list[Skip] = []

    for idx, raw in enumerate(deps):
        dep_str = str(raw)
        name = _dep_name(dep_str)
        if not name or not _is_sm_package(name):
            continue
        if name in local:
            skips.append(Skip(path, name, "workspace/local source"))
            continue
        latest = cache.get(name)
        if latest is None:
            skips.append(Skip(path, name, "not found on PyPI"))
            continue
        result = rewrite_requirement(dep_str, latest, loosen=loosen)
        if result.spec is None:
            if result.reason:
                skips.append(Skip(path, name, result.reason))
            continue
        deps[idx] = result.spec
        changes.append(Change(path, name, dep_str.strip(), result.spec))

    return changes, skips, doc if changes else None


def _print_summary(changes: list[Change], skips: list[Skip], dry_run: bool) -> None:
    if not changes and not skips:
        typer.echo("No simple_module_* dependencies found.")
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
        typer.echo(f"\n{verb} {len(changes)} dependency(ies) across {len(by_file)} file(s).")
        if not dry_run:
            typer.echo("Run `uv sync` to apply.")
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
    root = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    if not root.is_file():
        typer.echo(f"ERROR: {root} not found.", err=True)
        raise typer.Exit(code=1)

    fetch = fetcher or default_fetcher
    root_doc = tomlkit.parse(root.read_text(encoding="utf-8"))
    files: list[tuple[Path, tomlkit.TOMLDocument]] = [(root, root_doc)]
    for member in _workspace_member_dirs(root, root_doc):
        files.append((member, tomlkit.parse(member.read_text(encoding="utf-8"))))

    # Pre-fetch all unique sm packages in parallel — PyPI calls dominate runtime.
    unique_names = sorted({n for _, doc in files for n in _collect_sm_deps(doc)})
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
    pending: list[tuple[Path, tomlkit.TOMLDocument]] = []

    for file, doc in files:
        changes, skips, new_doc = _process_file(file, doc, cache=cache, loosen=loosen)
        all_changes.extend(changes)
        all_skips.extend(skips)
        if new_doc is not None:
            pending.append((file, new_doc))

    if not dry_run:
        for file, doc in pending:
            file.write_text(tomlkit.dumps(doc), encoding="utf-8")

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
            help="Rewrite every constraint to `>=<latest>` instead of keeping its operator.",
        ),
    ] = False,
) -> None:
    """Update all simple_module_* dependencies to the latest PyPI versions.

    Each constraint keeps the operator it already has — `==0.0.32` becomes
    `==0.0.33`, `>=0.0.32` becomes `>=0.0.33` — so bumping versions never
    silently changes a project's pinning policy. A dependency whose upper
    bound excludes the latest release is reported and left alone. Pass
    `--loosen` to rewrite everything to `>=<latest>` instead.
    """
    run_update(path, dry_run=dry_run, include_pre=include_pre, loosen=loosen)
