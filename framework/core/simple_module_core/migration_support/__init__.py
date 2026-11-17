"""Migration discovery. Keep core and the standalone CLI's vendored copy identical."""

import os
from importlib.metadata import EntryPoints, entry_points
from pathlib import Path

NO_ALEMBIC_CONFIG = "No Alembic config found. Provide alembic.ini or host/alembic.ini."
_PROJECT_WALK_LIMIT = 4
_PROJECT_MARKERS = (".git", ".env.example", ".env")


def resolve_project_root(*, fallback: Path | None = None) -> Path:
    """Find the host project from cwd, including from an inner workspace package."""
    override = os.environ.get("SM_PROJECT_ROOT")
    if override:
        return Path(override)

    cwd = Path.cwd()
    package_root = None
    try:
        home = Path.home()
    except RuntimeError:
        home = None
    for depth, root in enumerate((cwd, *cwd.parents[:_PROJECT_WALK_LIMIT])):
        if root == home or (root != cwd and root.stat().st_mode & 0o002):
            break
        if any((root / marker).exists() for marker in _PROJECT_MARKERS):
            return root
        if (root / "alembic.ini").is_file():
            # A workspace root may also have a flat config, which takes precedence.
            parent = root.parent
            if (
                root.name == "host"
                and depth < _PROJECT_WALK_LIMIT
                and parent != home
                and not parent.stat().st_mode & 0o002
                and any(
                    (parent / marker).exists()
                    for marker in (*_PROJECT_MARKERS, "pyproject.toml", "alembic.ini")
                )
            ):
                return parent
            return root
        if (root / "host/alembic.ini").is_file():
            return root
        if package_root is None and (root / "pyproject.toml").is_file():
            package_root = root
    return package_root or fallback or cwd


def resolve_alembic_ini(
    project_root: str | Path | None = None, *, override: str | Path | None = None
) -> Path | None:
    """Find the host's ini. An explicit path is cwd-relative and disables fallback."""
    if override is not None:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    root = Path(project_root) if project_root is not None else resolve_project_root()
    for candidate in (root / "alembic.ini", root / "host" / "alembic.ini"):
        if candidate.is_file():
            return candidate
    return None


def data_upgrade_entry_points() -> EntryPoints:
    """Find registered recipes without importing any recipe code."""
    return entry_points(group="simple_module.data_upgrades")
