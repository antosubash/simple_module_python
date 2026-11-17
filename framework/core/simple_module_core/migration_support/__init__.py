"""Migration discovery shared with the standalone CLI through a source symlink."""

import os
from importlib.metadata import EntryPoints, entry_points
from pathlib import Path

NO_ALEMBIC_CONFIG = "No Alembic config found. Provide alembic.ini or host/alembic.ini."


def resolve_alembic_ini(
    project_root: str | Path | None = None, *, override: str | Path | None = None
) -> Path | None:
    """Find the host's ini. An explicit path is cwd-relative and disables fallback."""
    if override is not None:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    root = Path(project_root or os.environ.get("SM_PROJECT_ROOT") or Path.cwd())
    for candidate in (root / "alembic.ini", root / "host" / "alembic.ini"):
        if candidate.is_file():
            return candidate
    return None


def data_upgrade_entry_points() -> EntryPoints:
    """Find registered recipes without importing any recipe code."""
    return entry_points(group="simple_module.data_upgrades")
