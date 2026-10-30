"""Python manifest discovery and dependency planning for package-update."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Array

from simple_module_cli.requirements import parse_requirement, rewrite_requirement


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


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _is_sm_package(name: str) -> bool:
    return _normalize(name).startswith("simple-module-")


def _dep_name(spec: str) -> str | None:
    """Extract the distribution name from a PEP 508 requirement string."""
    parsed = parse_requirement(spec)
    return parsed.name if parsed else None


def _is_local_source(source: Any) -> bool:
    if isinstance(source, (list, Array)):
        return any(_is_local_source(item) for item in source)
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
    return list(dict.fromkeys(p.resolve() for p in out))


def source_map(doc: tomlkit.TOMLDocument) -> dict[str, Any]:
    return {_normalize(name): src for name, src in (_get_uv_section(doc, "sources") or {}).items()}


def local_sources(doc: tomlkit.TOMLDocument, inherited: dict[str, Any]) -> set[str]:
    sources = {**inherited, **source_map(doc)}
    return {name for name, source in sources.items() if _is_local_source(source)}


def _dependency_arrays(doc: tomlkit.TOMLDocument):
    project = doc.get("project", {})
    if isinstance(project, dict):
        deps = project.get("dependencies")
        if isinstance(deps, (list, Array)):
            yield deps
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for deps in optional.values():
                if isinstance(deps, (list, Array)):
                    yield deps
    groups = doc.get("dependency-groups", {})
    if isinstance(groups, dict):
        for deps in groups.values():
            if isinstance(deps, (list, Array)):
                yield deps


def _collect_sm_deps(doc: tomlkit.TOMLDocument, local: set[str]) -> list[str]:
    return [
        name
        for deps in _dependency_arrays(doc)
        for raw in deps
        if isinstance(raw, str)
        and (name := _dep_name(raw))
        and _is_sm_package(name)
        and _normalize(name) not in local
    ]


def _process_file(
    path: Path,
    doc: tomlkit.TOMLDocument,
    *,
    cache: dict[str, str | None],
    loosen: bool = False,
    local: set[str],
) -> tuple[list[Change], list[Skip], tomlkit.TOMLDocument | None]:
    changes: list[Change] = []
    skips: list[Skip] = []

    for deps in _dependency_arrays(doc):
        for idx, raw in enumerate(deps):
            if not isinstance(raw, str):
                continue
            dep_str = raw
            name = _dep_name(dep_str)
            if not name or not _is_sm_package(name):
                continue
            if _normalize(name) in local:
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
