"""Real data for the Doctor screen — the in-app mirror of ``make doctor``.

Everything here reads live state: the same diagnostics engine the dev boot
runs (SM001-SM023), the migration state the lifespan already checked, and the
alembic script directory for recent revisions. Nothing is sampled or mocked —
if a panel has no real source it does not render.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from simple_module_core.diagnostics import run_diagnostics

logger = logging.getLogger(__name__)


def _relative(file: str | None) -> str | None:
    """Trim the working directory off absolute finding paths for display."""
    if not file:
        return file
    try:
        return str(Path(file).relative_to(Path.cwd()))
    except ValueError:
        return file


_ALEMBIC_INI = "host/alembic.ini"
_RECENT_LIMIT = 5


def collect_diagnostics(app: FastAPI) -> list[dict[str, Any]]:
    """Run the module + i18n diagnostics and serialize the findings.

    Mirrors the dev-boot run in ``app_builder.create_app`` (minus the host/ui
    locale extras, which only the builder can see). Sorted errors-first so the
    screen leads with what needs fixing.
    """
    sm = app.state.sm
    diagnostics = run_diagnostics(
        list(sm.modules),
        i18n_supported_locales=sm.settings.i18n_supported_locales,
        i18n_default_locale=sm.settings.i18n_default_locale,
    )
    order = {"error": 0, "warning": 1, "info": 2}
    diagnostics.sort(key=lambda d: (order.get(d.level.value, 3), d.code))
    return [
        {
            "level": d.level.value,
            "code": d.code,
            "message": d.message,
            "module": d.module_name,
            "file": _relative(d.file),
            "suggestion": d.suggestion,
        }
        for d in diagnostics
    ]


def migration_overview(app: FastAPI) -> dict[str, Any]:
    """Migration state from the boot check, plus the most recent revisions.

    ``app.state.migration`` exists because the lifespan refuses to start a
    behind-head app, so a running app is at head by construction — the value
    of this panel is showing *which* head, and what recently changed.
    """
    state = getattr(app.state, "migration", None) or {}
    return {
        "current_revision": state.get("current_revision"),
        "head_revision": state.get("head_revision"),
        "is_current": state.get("is_current", True),
        "recent": _recent_revisions(),
    }


def _recent_revisions(limit: int = _RECENT_LIMIT) -> list[dict[str, Any]]:
    """Newest ``limit`` alembic revisions (head first), or ``[]`` when the
    script directory isn't present (e.g. a deployment without host/)."""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(AlembicConfig(_ALEMBIC_INI))
        revisions = []
        for rev in script.walk_revisions():
            revisions.append(
                {
                    "revision": rev.revision[:12],
                    "message": rev.doc or "",
                    "modules": sorted(rev.branch_labels or ()),
                }
            )
            if len(revisions) >= limit:
                break
        return revisions
    except Exception as exc:  # pragma: no cover - depends on deploy layout
        logger.debug("Alembic script directory unavailable: %s", exc)
        return []


def environment_info(app: FastAPI) -> dict[str, Any]:
    """Live environment facts: mode, database backend, locales."""
    sm = app.state.sm
    return {
        "environment": sm.settings.environment,
        "database": sm.db.engine.dialect.name,
        "locales": list(sm.settings.i18n_supported_locales),
        "default_locale": sm.settings.i18n_default_locale,
    }
