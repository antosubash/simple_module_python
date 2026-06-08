"""Greenfield ``simple-module new`` scaffolding.

Wraps :func:`simple_module_cli.scaffolding.create_host` (and, in
workspace mode, :func:`create_workspace`) with the opinionated bits —
module-list resolution from the CLI catalog, secret generation, DB URL
selection, ``pyproject.toml`` / ``package.json`` rewriting, and
post-scaffold recipe application.

Lives in its own module to keep ``scaffolding.py`` under the per-file
line cap and to make the surface area of "host scaffold" vs "app
scaffold" obvious to readers.
"""

from __future__ import annotations

import json as _json
import secrets as _secrets
import shutil as _shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from simple_module_cli._env import set_env_key
from simple_module_cli.case import to_kebab_case, to_pascal_case
from simple_module_cli.catalog import CATALOG, PRESETS, expand_deps
from simple_module_cli.recipes import RECIPES, ScaffoldCtx
from simple_module_cli.scaffolding import (
    SAFE_PRESERVED_NAMES,
    _module_to_pypi_name,
    create_host,
    create_module,
    create_workspace,
    resolve_framework_version,
)

__all__ = ["create_app_project"]

_SAMPLE_MODULE_NAME = "hello"
_SAMPLE_MODULE_PKG = _module_to_pypi_name(_SAMPLE_MODULE_NAME)


_FRAMEWORK_VERSION = resolve_framework_version()

# Pin ``simple_module_cli`` as a dev dep so ``uv run smpy`` resolves to the
# project venv. The global ``uv tool`` install runs in its own isolated venv
# that can't see the project's plugin entry points (issue #134). The lint /
# test tooling (ruff, ty, pytest-*) backs the generated `make lint`/`make
# test` targets so a fresh app can run its own quality gates.
_APP_PY_DEV_DEPS = [
    f"simple_module_test=={_FRAMEWORK_VERSION}",
    f"simple_module_cli=={_FRAMEWORK_VERSION}",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-playwright>=0.7.2",
    "ruff>=0.8",
    "ty>=0.0.29",
]

_APP_NPM_DEPS = {
    "@simple-module-py/ui": _FRAMEWORK_VERSION,
    "@simple-module-py/i18n": _FRAMEWORK_VERSION,
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^2.0.0",
}
_APP_NPM_DEV_DEPS = {
    "@simple-module-py/tsconfig": _FRAMEWORK_VERSION,
    "@vitejs/plugin-react": "^5.0.0",
    "typescript": "^5.6.0",
    "vite": "^8.0.0",
}

# Files the host template ships that the workspace template re-emits at
# the project root. Host copies are stripped in workspace mode.
_HOST_FILES_OWNED_BY_WORKSPACE = (
    ".env.example",
    ".gitignore",
    "README.md",
    "Makefile",
)


def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
    flat: bool = False,
) -> tuple[Path, list[Path]]:
    """Greenfield ``simple-module new`` scaffold.

    Workspace mode (default) lays down a uv + npm workspace at ``target/``
    with the host under ``target/host/`` and a sample module under
    ``target/modules/hello/``. Flat mode keeps the legacy single-host layout.
    Tolerates ``SAFE_PRESERVED_NAMES`` at ``target`` (leftovers from
    ``git init`` / ``gh repo create`` / IDE setup); other pre-existing
    entries raise ``FileExistsError``.

    Returns ``(host_dir, preserved)`` — the host directory (``target`` in
    flat mode, ``target/host`` in workspace mode) and the paths whose
    scaffold copy was skipped because the user already had one.
    """
    chosen = list(selected) if selected is not None else list(PRESETS["standard"])
    resolved, _added = expand_deps(chosen)

    display_names = [to_pascal_case(CATALOG[m].display) for m in resolved]
    host_dir = target if flat else target / "host"
    preserved: list[Path] = []
    if not flat:
        preserved.extend(
            create_workspace(
                target,
                name=name,
                framework_version=_FRAMEWORK_VERSION,
                preserve_existing=SAFE_PRESERVED_NAMES,
            )
        )
    preserved.extend(
        create_host(
            host_dir,
            name=name,
            modules=display_names,
            framework_version=_FRAMEWORK_VERSION,
            preserve_existing=SAFE_PRESERVED_NAMES if flat else frozenset(),
        )
    )
    if not flat:
        _strip_workspace_owned_files(host_dir)

    py_deps = [f"simple_module_hosting=={_FRAMEWORK_VERSION}"] + [
        f"{CATALOG[m].package}=={_FRAMEWORK_VERSION}" for m in resolved
    ]

    workspace_sources: list[str] = []
    if not flat:
        _scaffold_sample_module(target)
        py_deps.append(_SAMPLE_MODULE_PKG)
        workspace_sources.append(_SAMPLE_MODULE_PKG)

    env_path = target / ".env.example"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    env_text = set_env_key(env_text, "SM_SECRET_KEY", _secrets.token_urlsafe(32))
    env_text = set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, to_kebab_case(name), flat=flat))
    env_text = set_env_key(env_text, "SM_MULTI_TENANT", "true" if tenancy else "false")
    env_path.write_text(env_text, encoding="utf-8")

    host_pyproject = host_dir / "pyproject.toml"
    text = host_pyproject.read_text(encoding="utf-8")
    # Workspace mode needs the host's [project].name distinct from the
    # workspace root's, otherwise uv refuses with "two workspace members
    # are both named ...". Flat mode keeps the user's exact name.
    project_name = None if flat else f"{to_kebab_case(name)}-host"
    text = _rewrite_pyproject(
        text, py_deps, _APP_PY_DEV_DEPS, sources=workspace_sources, project_name=project_name
    )
    host_pyproject.write_text(text, encoding="utf-8")

    if flat:
        # The workspace template already emits a top-level package.json
        # with workspaces; flat mode has none, so seed one with the
        # framework npm pins so `npm install` resolves at the root.
        pkg_path = target / "package.json"
        pkg_data: dict[str, Any] = (
            _json.loads(pkg_path.read_text(encoding="utf-8"))
            if pkg_path.exists()
            else {"name": to_kebab_case(name), "private": True, "type": "module"}
        )
        pkg_data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
        pkg_data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
        pkg_path.write_text(_json.dumps(pkg_data, indent=2) + "\n", encoding="utf-8")

    ctx = ScaffoldCtx(name=name, db=db, tenancy=tenancy, selected=tuple(resolved))
    for mod_name in resolved:
        recipe_key = CATALOG[mod_name].recipe
        if recipe_key is not None and recipe_key in RECIPES:
            RECIPES[recipe_key].apply(target, ctx)

    return host_dir, preserved


def _strip_workspace_owned_files(host_dir: Path) -> None:
    """Drop host copies of files the workspace root owns in workspace mode."""
    for relpath in _HOST_FILES_OWNED_BY_WORKSPACE:
        (host_dir / relpath).unlink(missing_ok=True)


def _scaffold_sample_module(target: Path) -> None:
    sample_dest = target / "modules" / _SAMPLE_MODULE_NAME
    if sample_dest.exists():
        return
    # Pin the sample's framework deps to the exact framework version so the
    # workspace resolves (the template's >=1.0,<2.0 ranges don't exist on PyPI
    # pre-1.0). See GH #195.
    create_module(sample_dest, name=_SAMPLE_MODULE_NAME, framework_version=_FRAMEWORK_VERSION)
    # GitHub only reads workflows from the repo root, so the template's
    # .github/ is dead inside a workspace.
    _shutil.rmtree(sample_dest / ".github")
    _seed_static_dist_placeholder(sample_dest / _SAMPLE_MODULE_NAME / "static" / "dist")


def _seed_static_dist_placeholder(static_dist: Path) -> None:
    # Hatch's force-include resolves at build time even for editable installs;
    # an empty placeholder keeps `uv sync` from failing before vite build runs.
    static_dist.mkdir(parents=True, exist_ok=True)
    (static_dist / ".gitkeep").touch()


def _db_url(db: str, slug: str, *, flat: bool) -> str:
    if db == "postgres":
        return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{slug}"
    # Workspace mode keeps the SQLite file next to host/'s alembic.ini so
    # `cd host && uvicorn` and `cd host && alembic` resolve the same path.
    return "sqlite+aiosqlite:///./app.db" if flat else "sqlite+aiosqlite:///./host/app.db"


def _rewrite_pyproject(
    text: str,
    deps: list[str],
    dev_deps: list[str],
    *,
    sources: Sequence[str] = (),
    project_name: str | None = None,
) -> str:
    """Replace deps in a host ``pyproject.toml`` and pin workspace sources.

    ``sources`` lists ``simple_module_*`` packages that should resolve from
    the uv workspace (``modules/*``) instead of PyPI. Emits a
    ``[tool.uv.sources]`` block per entry. Empty in flat mode.

    ``project_name`` overrides ``[project].name`` — set in workspace mode
    so the host's package name differs from the workspace root's.
    """
    import tomlkit

    doc = tomlkit.parse(text)
    project = doc.setdefault("project", tomlkit.table())
    if project_name is not None:
        project["name"] = project_name
    project["dependencies"] = list(deps)
    groups = doc.setdefault("dependency-groups", tomlkit.table())
    groups["dev"] = list(dev_deps)
    if sources:
        tool = doc.setdefault("tool", tomlkit.table())
        uv_table = tool.setdefault("uv", tomlkit.table())
        uv_sources = uv_table.setdefault("sources", tomlkit.table())
        for src in sources:
            uv_sources[src] = {"workspace": True}
    return tomlkit.dumps(doc)
