"""Public boot sequence for host entry points."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI


def build_host_app(
    entry_file: str | Path,
    *,
    project_root: str | Path | None = None,
    routers: Iterable[APIRouter | str] = (),
) -> FastAPI:
    """Load the host environment, merge DB settings, configure logging and build.

    Pass ``__file__`` from the host entry point. For ``host/main.py`` the root
    is the host directory's parent; for a flat ``main.py`` it is its directory.
    This rule is independent of cwd and project markers. ``project_root``
    overrides that default; an existing ``SM_PROJECT_ROOT``
    takes precedence and absolute values are preserved. Relative overrides are
    made absolute before changing cwd. The entry file's directory is pinned on
    sys.path so sibling imports survive the cwd change.

    Routers can be APIRouter instances or ``module:attribute`` import strings.
    Use strings when a router imports settings: dotenv must populate os.environ
    before *any* settings or application imports, including direct env readers.
    Real environment values always win over dotenv values. Development extras
    installed by create_app remain development-only; app-specific mounts can
    inspect ``app.state.sm.settings`` after this call.
    """
    host_dir = Path(entry_file).resolve().parent
    if str(host_dir) not in sys.path:
        sys.path.insert(0, str(host_dir))

    from simple_module_core.dotenv import load_dotenv_into_environ

    root_env = os.environ.get("SM_PROJECT_ROOT")
    root = root_env or project_root
    if root is None:
        root = host_dir.parent if host_dir.name == "host" else host_dir
    root = Path(root).resolve()
    if not root_env or not Path(root_env).is_absolute():
        os.environ["SM_PROJECT_ROOT"] = str(root)
    os.chdir(root)
    load_dotenv_into_environ(root / ".env")

    from simple_module_hosting import create_app, merge_host_settings
    from simple_module_hosting.logging import setup_logging

    settings = merge_host_settings()
    setup_logging(level=settings.log_level, json_format=settings.log_format == "json")
    app = create_app(settings)
    for router in routers:
        if isinstance(router, str):
            module, attribute = router.split(":", 1)
            router = getattr(import_module(module), attribute)
        app.include_router(router)
    return app
