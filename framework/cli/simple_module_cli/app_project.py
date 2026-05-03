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
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from simple_module_cli._env import set_env_key
from simple_module_cli.case import to_kebab_case, to_pascal_case
from simple_module_cli.catalog import CATALOG, PRESETS, expand_deps
from simple_module_cli.recipes import RECIPES, ScaffoldCtx
from simple_module_cli.scaffolding import (
    _module_to_pypi_name,
    create_host,
    create_module,
    create_workspace,
)

__all__ = ["create_app_project"]

_SAMPLE_MODULE_NAME = "hello"
_SAMPLE_MODULE_PKG = _module_to_pypi_name(_SAMPLE_MODULE_NAME)


def _resolve_framework_version() -> str:
    """Resolve the framework version to pin scaffolded apps against.

    The CLI ships in lockstep with the rest of the framework (one
    ``bump_version.py`` rewrites every ``pyproject.toml`` in the repo), so
    its own installed version is the source of truth. Falling back to a
    placeholder lets editable installs without dist-info still scaffold —
    but that path should never be reached in a release wheel.
    """
    try:
        return _pkg_version("simple_module_cli")
    except PackageNotFoundError:
        return "0.0.0"


_FRAMEWORK_VERSION = _resolve_framework_version()

_APP_PY_DEV_DEPS = [f"simple_module_test=={_FRAMEWORK_VERSION}", "pytest>=8.0"]

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
_HOST_FILES_OWNED_BY_WORKSPACE = (".env.example", ".gitignore", "README.md")


def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
    flat: bool = False,
) -> None:
    """Greenfield ``simple-module new`` scaffold.

    In workspace mode (the default), lays down a uv + npm workspace at
    ``target/`` with the host under ``target/host/`` and a sample module
    under ``target/modules/hello/``. In flat mode (``flat=True``), keeps
    the legacy single-host layout: host files at ``target/`` with no
    ``modules/`` directory or workspace plumbing.

    Generates a secret, picks a DB URL, rewrites the host's
    ``pyproject.toml`` / the relevant ``package.json`` to pin exact
    framework versions, and applies any matching post-scaffold recipes
    (e.g. the ``background_tasks`` recipe drops a Celery worker stack).
    """
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            f"Destination {target} already exists and is non-empty; "
            "choose a new path or remove its contents first."
        )

    chosen = list(selected) if selected is not None else list(PRESETS["standard"])
    resolved, _added = expand_deps(chosen)

    display_names = [to_pascal_case(CATALOG[m].display) for m in resolved]
    host_dir = target if flat else target / "host"
    if not flat:
        target.mkdir(parents=True, exist_ok=True)
        create_workspace(target, name=name)
    create_host(host_dir, name=name, modules=display_names, framework_version=_FRAMEWORK_VERSION)
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
        _write_flat_top_level_package_json(target, name=name)

    ctx = ScaffoldCtx(name=name, db=db, tenancy=tenancy, selected=tuple(resolved))
    for mod_name in resolved:
        recipe_key = CATALOG[mod_name].recipe
        if recipe_key is not None and recipe_key in RECIPES:
            RECIPES[recipe_key].apply(target, ctx)


def _strip_workspace_owned_files(host_dir: Path) -> None:
    """Drop host copies of files the workspace root owns in workspace mode."""
    for relpath in _HOST_FILES_OWNED_BY_WORKSPACE:
        (host_dir / relpath).unlink(missing_ok=True)


def _scaffold_sample_module(target: Path) -> None:
    sample_dest = target / "modules" / _SAMPLE_MODULE_NAME
    if sample_dest.exists():
        return
    create_module(sample_dest, name=_SAMPLE_MODULE_NAME)
    _pin_sample_module_deps(sample_dest)
    # Hatch's force-include directive resolves at build time even for
    # editable installs; an empty placeholder dir keeps `uv sync` from
    # failing before the user has run vite build.
    static_dist = sample_dest / _SAMPLE_MODULE_NAME / "static" / "dist"
    static_dist.mkdir(parents=True, exist_ok=True)
    (static_dist / ".gitkeep").touch()


def _pin_sample_module_deps(sample_dest: Path) -> None:
    """Replace the module template's future-API range pins with exact pins.

    The shared ``sm create-module`` template ships ``>=1.0,<2.0`` against the
    framework's eventual stable line, but the workspace-bundled sample has to
    resolve against whatever the framework version actually is today (``==X``
    in pre-1.0). Without rewriting, ``uv sync`` can't satisfy the workspace.
    """
    import tomlkit

    pyproject = sample_dest / "pyproject.toml"
    doc = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    project = doc["project"]
    project["dependencies"] = [_pin_or_keep(dep) for dep in project.get("dependencies", [])]
    optional = project.get("optional-dependencies")
    if optional is not None:
        for extra, deps in list(optional.items()):
            optional[extra] = [_pin_or_keep(dep) for dep in deps]
    pyproject.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _pin_or_keep(dep: str) -> str:
    """Pin a ``simple_module_*`` requirement to the framework version; pass through otherwise."""
    pkg = dep.split(">=", 1)[0].split("==", 1)[0].split("<", 1)[0].strip()
    if pkg.startswith("simple_module_") or pkg.startswith("simple-module-"):
        return f"{pkg}=={_FRAMEWORK_VERSION}"
    return dep


def _write_flat_top_level_package_json(target: Path, *, name: str) -> None:
    """In flat mode the host template doesn't ship a top-level ``package.json``.

    Create one so ``npm install`` from the project root resolves the
    framework npm deps. Workspace mode doesn't need this — the workspace
    template already emits a workspaces-aware top-level package.json.
    """
    pkg_path = target / "package.json"
    data: dict[str, Any]
    if pkg_path.exists():
        data = _json.loads(pkg_path.read_text(encoding="utf-8"))
    else:
        data = {"name": to_kebab_case(name), "private": True, "type": "module"}
    data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
    data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
    pkg_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
