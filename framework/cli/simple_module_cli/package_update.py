"""``sm package-update`` — bump simple_module_* deps to latest PyPI versions.

Walks the project's ``pyproject.toml`` (and any ``[tool.uv.workspace]`` members),
finds every dependency whose distribution name starts with ``simple_module_`` /
``simple-module-``, queries PyPI for the latest non-yanked release, and rewrites
the constraint to ``name>=<latest>``.

Dependencies whose ``[tool.uv.sources]`` entry points at a workspace member, a
local path, a git ref, or a URL are left untouched — those aren't installed
from PyPI.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import tomlkit
import typer
from tomlkit.items import Array, Table

__all__ = ["package_update", "run_update"]

Fetcher = Callable[[str], dict[str, Any]]

_PYPI_URL = "https://pypi.org/pypi/{name}/json"
_SM_PREFIX_RE = re.compile(r"^simple[_-]module[_-]", re.IGNORECASE)
# PEP 440 release segments contain only digits + dots; any letter signals
# a pre/post/dev release (a, b, rc, post, dev). Coarser than packaging.version
# but `packaging` isn't a CLI dep (see test_no_framework_deps.py).
_PRE_RELEASE_RE = re.compile(r"[a-zA-Z]")
_REQ_OPS = ("===", "==", ">=", "<=", "!=", "~=", ">", "<")


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
    base = spec.split(";", 1)[0].strip()
    base = base.split("[", 1)[0]
    for op in _REQ_OPS:
        if op in base:
            base = base.split(op, 1)[0]
            break
    name = base.strip()
    return name or None


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


def _fetch_latest(name: str, *, include_pre: bool, fetcher: Fetcher) -> str | None:
    try:
        data = fetcher(_PYPI_URL.format(name=name))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None
    releases = data.get("releases") or {}
    candidates: list[str] = []
    for version, files in releases.items():
        if not files:
            continue
        if any(f.get("yanked") for f in files):
            continue
        if not include_pre and _PRE_RELEASE_RE.search(version):
            continue
        candidates.append(version)
    if candidates:
        return max(candidates, key=_version_key)
    info = data.get("info") or {}
    return info.get("version")


def _version_key(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in v.split("."):
        digits = re.match(r"\d+", part)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def _default_fetcher(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        new_dep = f"{name}>={latest}"
        if new_dep == dep_str.strip():
            continue
        deps[idx] = new_dep
        changes.append(Change(path, name, dep_str.strip(), new_dep))

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
    fetcher: Fetcher | None = None,
) -> None:
    """Programmatic entry point — separated from the Typer command for testing."""
    root = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    if not root.is_file():
        typer.echo(f"ERROR: {root} not found.", err=True)
        raise typer.Exit(code=1)

    fetch = fetcher or _default_fetcher
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
                lambda n: (n, _fetch_latest(n, include_pre=include_pre, fetcher=fetch)),
                unique_names,
            )
            cache = dict(results)

    all_changes: list[Change] = []
    all_skips: list[Skip] = []
    pending: list[tuple[Path, tomlkit.TOMLDocument]] = []

    for file, doc in files:
        changes, skips, new_doc = _process_file(file, doc, cache=cache)
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
) -> None:
    """Update all simple_module_* dependencies to the latest PyPI versions."""
    run_update(path, dry_run=dry_run, include_pre=include_pre)
