"""Where the host project lives: anchors static files and i18n catalogs."""

from __future__ import annotations

from pathlib import Path

from simple_module_core.migrations.support import resolve_project_root as _resolve_project_root


def resolve_project_root() -> Path:
    """Find the host root, falling back to the checkout for in-tree development."""
    return _resolve_project_root(fallback=Path(__file__).resolve().parents[3])
