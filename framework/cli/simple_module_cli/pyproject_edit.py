"""tomlkit edits for a host ``pyproject.toml`` — deps + [tool.uv.sources].

Format-preserving: comments and layout in the host file survive the edit.
Callers write nothing until resolution has succeeded (spec §6): build the
document in memory, then ``save_pyproject`` once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Array, Table

from simple_module_cli.git_source import RefInfo

__all__ = [
    "dep_constraint",
    "git_sources",
    "has_git_sources",
    "load_pyproject",
    "save_pyproject",
    "write_dependency",
    "write_git_source",
    "write_path_source",
]


def load_pyproject(path: Path) -> tomlkit.TOMLDocument:
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def save_pyproject(path: Path, doc: tomlkit.TOMLDocument) -> None:
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _dependencies(doc: tomlkit.TOMLDocument) -> Array:
    project = doc.get("project")
    if not isinstance(project, (dict, Table)):
        raise ValueError("pyproject has no [project] table")
    deps = project.get("dependencies")
    if not isinstance(deps, (list, Array)):
        deps = tomlkit.array()
        deps.multiline(True)
        project["dependencies"] = deps
    return deps


def _dep_index(deps: Array, dist_name: str) -> int | None:
    key = dist_name.replace("-", "_").lower()
    for i, raw in enumerate(deps):
        text = str(raw).strip().replace("-", "_").lower()
        head = text
        for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
            head = head.split(sep, 1)[0]
        if head == key:
            return i
    return None


def dep_constraint(doc: tomlkit.TOMLDocument, dist_name: str) -> str | None:
    deps = _dependencies(doc)
    idx = _dep_index(deps, dist_name)
    if idx is None:
        return None
    text = str(deps[idx]).strip()
    for i, ch in enumerate(text):
        if ch in "<>=!~":
            return text[i:].strip()
    return None


def write_dependency(doc: tomlkit.TOMLDocument, dist_name: str, constraint: str) -> bool:
    deps = _dependencies(doc)
    entry = f"{dist_name}{constraint}"
    idx = _dep_index(deps, dist_name)
    if idx is None:
        deps.append(entry)
        return True
    if str(deps[idx]).strip() == entry:
        return False
    deps[idx] = entry
    return True


def _uv_sources(doc: tomlkit.TOMLDocument) -> Table:
    tool = doc.setdefault("tool", tomlkit.table(is_super_table=True))
    uv = tool.setdefault("uv", tomlkit.table(is_super_table=True))
    return uv.setdefault("sources", tomlkit.table())


def write_git_source(
    doc: tomlkit.TOMLDocument,
    dist_name: str,
    *,
    url: str,
    ref_info: RefInfo,
    subdirectory: str | None,
) -> bool:
    src = tomlkit.inline_table()
    src["git"] = url
    if ref_info.kind in ("tag", "branch", "rev") and ref_info.value:
        src[ref_info.kind] = ref_info.value
    if subdirectory:
        src["subdirectory"] = subdirectory
    sources = _uv_sources(doc)
    if dist_name in sources and dict(sources[dist_name]) == dict(src):
        return False
    sources[dist_name] = src
    return True


def write_path_source(doc: tomlkit.TOMLDocument, dist_name: str, *, path: str) -> bool:
    src = tomlkit.inline_table()
    src["path"] = path
    src["editable"] = True
    sources = _uv_sources(doc)
    if dist_name in sources and dict(sources[dist_name]) == dict(src):
        return False
    sources[dist_name] = src
    return True


def _sources_dict(doc: tomlkit.TOMLDocument) -> dict[str, Any]:
    tool = doc.get("tool")
    if not isinstance(tool, dict):
        return {}
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return {}
    sources = uv.get("sources")
    return dict(sources) if isinstance(sources, dict) else {}


def git_sources(doc: tomlkit.TOMLDocument) -> dict[str, dict]:
    return {
        name: dict(src)
        for name, src in _sources_dict(doc).items()
        if isinstance(src, dict) and "git" in src
    }


def has_git_sources(doc: tomlkit.TOMLDocument) -> bool:
    return bool(git_sources(doc))
