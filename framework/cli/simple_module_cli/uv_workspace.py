"""Detect membership in an enclosing uv workspace.

uv rejects a ``{path = ...}`` source for a package that is a workspace member
(it must be ``{ workspace = true }``), so ``smpy add`` needs to know whether a
local module lives inside the workspace its host belongs to. See GH #442.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

__all__ = ["find_workspace_root", "is_workspace_member"]


def _workspace_table(pyproject: Path) -> dict | None:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    table = data.get("tool", {}).get("uv", {}).get("workspace")
    return table if isinstance(table, dict) else None


def find_workspace_root(start: Path) -> Path | None:
    """Nearest ancestor of ``start`` (inclusive) whose pyproject has ``[tool.uv.workspace]``."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and _workspace_table(pyproject) is not None:
            return candidate
    return None


def _expand(root: Path, patterns: object) -> set[Path]:
    if not isinstance(patterns, list):
        return set()
    found: set[Path] = set()
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        for match in root.glob(pattern):
            if match.is_dir():
                found.add(match.resolve())
    return found


def is_workspace_member(project_dir: Path, module_dir: Path) -> bool:
    """True if ``module_dir`` is a member of the uv workspace enclosing ``project_dir``."""
    root = find_workspace_root(project_dir)
    if root is None:
        return False
    table = _workspace_table(root / "pyproject.toml") or {}
    members = _expand(root, table.get("members"))
    excluded = _expand(root, table.get("exclude"))
    target = module_dir.resolve()
    return target in members and target not in excluded
