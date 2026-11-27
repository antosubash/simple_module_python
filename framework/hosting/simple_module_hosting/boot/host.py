"""Public boot sequence for host entry points."""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Callable, Iterable, Iterator
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from simple_module_db import DatabaseState

    from simple_module_hosting.config.settings import Settings


def _is_workspace_member(host_dir: Path) -> bool:
    """True for ``<root>/host/main.py`` under a uv workspace root (repo and workspace scaffold).

    A flat project keeps ``main.py`` in its own root, even when that directory is named
    ``host``; only a parent ``pyproject.toml`` declaring ``[tool.uv.workspace]`` makes the
    parent the project root. Markers such as ``.git`` are not used: images drop them.
    """
    if host_dir.name != "host":
        return False
    try:
        with (host_dir.parent / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(data.get("tool", {}).get("uv", {}).get("workspace"), dict)


def build_host_app(
    entry_file: str | Path,
    *,
    app_name: str | None = None,
    project_root: str | Path | None = None,
    routers: Iterable[APIRouter | str] = (),
    database: DatabaseState | Callable[[Settings], DatabaseState] | None = None,
    customize: Callable[[FastAPI], None] | None = None,
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
    They are mounted before modules' ``register_fallback_routes`` hooks.
    Use strings when a router imports settings: dotenv must populate os.environ
    before *any* settings or application imports, including direct env readers.
    Real environment values always win over dotenv values. Development extras
    installed by create_app remain development-only; app-specific mounts can
    inspect ``app.state.sm.settings`` after this call.

    ``database`` is passed to ``create_app`` after settings resolve. Supplied
    states and factory results remain caller-owned; dispose their engines yourself.
    ``customize(app)`` runs after all module registration hooks, with
    ``app.state.sm`` available, before the outer middleware pipeline is finished.
    ``app_name`` defaults the API title and application identity below env/DB values.
    """
    host_dir = Path(entry_file).resolve().parent
    if str(host_dir) not in sys.path:
        sys.path.insert(0, str(host_dir))

    from simple_module_core.settings.dotenv import load_dotenv_into_environ

    root_env = os.environ.get("SM_PROJECT_ROOT")
    root = root_env or project_root
    if root is None:
        root = host_dir.parent if _is_workspace_member(host_dir) else host_dir
    root = Path(root).resolve()
    if not root_env or not Path(root_env).is_absolute():
        os.environ["SM_PROJECT_ROOT"] = str(root)
    os.chdir(root)
    load_dotenv_into_environ(root / ".env")

    from simple_module_hosting import create_app, merge_host_settings
    from simple_module_hosting.observability.logging import setup_logging

    settings = (
        merge_host_settings(app_name=app_name) if app_name is not None else merge_host_settings()
    )
    setup_logging(level=settings.log_level, json_format=settings.log_format == "json")
    options: dict[str, Any] = {"database": database} if database is not None else {}
    if customize is not None:
        options["customize"] = customize
    return create_app(settings, routers=_resolve_routers(routers), **options)


def _resolve_routers(routers: Iterable[APIRouter | str]) -> Iterator[APIRouter]:
    # Resolve lazily, after environment and module registrations, as before.
    for router in routers:
        if isinstance(router, str):
            module, attribute = router.split(":", 1)
            router = getattr(import_module(module), attribute)
        yield router
