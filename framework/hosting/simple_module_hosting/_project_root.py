"""Where the host project lives: anchors static files and i18n catalogs."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PROJECT_ROOT = "SM_PROJECT_ROOT"


_PROJECT_ROOT_SENTINELS = ("pyproject.toml", ".env", "alembic.ini")


def resolve_project_root() -> Path:
    """Return the project root directory.

    Prefers the ``SM_PROJECT_ROOT`` environment variable when set.

    Otherwise walks up from the current working directory looking for a
    project sentinel (``pyproject.toml``, ``.env`` or ``alembic.ini``). This
    works whether the framework is installed as a wheel into ``site-packages``
    or run from a workspace clone.

    Falls back to ``parents[3]`` for the in-tree dev loop only when the walk
    finds nothing — which still keeps ``framework/`` users working without
    setting the env var explicitly.

    Compare ``simple_module_core.dotenv.find_env_file``: both honor
    ``SM_PROJECT_ROOT`` first, but this anchors the static/i18n root while
    that anchors which ``.env`` loads — different sentinels, kept separate.
    """
    override = os.environ.get(_ENV_PROJECT_ROOT)
    if override:
        return Path(override)
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if any((candidate / s).exists() for s in _PROJECT_ROOT_SENTINELS):
            return candidate
    return Path(__file__).resolve().parents[3]
