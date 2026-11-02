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
from pathlib import Path
from typing import Any

from simple_module_cli._app_project_manifests import (
    _APP_NPM_DEPS,
    _APP_NPM_DEV_DEPS,
    _APP_PY_DEV_DEPS,
    _FRAMEWORK_VERSION,
    _db_url,
    _rewrite_pyproject,
)
from simple_module_cli._env import set_env_key
from simple_module_cli._local_env import (
    add_postgres_password_placeholder,
    comment_out_env_key,
    write_local_env,
)
from simple_module_cli.case import to_kebab_case, to_pascal_case, to_snake_case
from simple_module_cli.catalog import CATALOG, PRESETS, expand_deps
from simple_module_cli.docker_assets import scaffold_docker_assets
from simple_module_cli.recipes import RECIPES, ScaffoldCtx
from simple_module_cli.scaffolding import (
    SAFE_PRESERVED_NAMES,
    _module_to_pypi_name,
    create_host,
    create_module,
    create_workspace,
)

__all__ = ["create_app_project"]

_SAMPLE_MODULE_NAME = "hello"
_SAMPLE_MODULE_PKG = _module_to_pypi_name(_SAMPLE_MODULE_NAME)

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

    # Generated secrets go to the gitignored .env, never the committed
    # .env.example (GH #441) — see write_local_env below.
    secret_keys = ["SM_SECRET_KEY"]
    if "users" in resolved:
        # UsersSettings refuses its placeholder token secrets when
        # SM_ENVIRONMENT=production — the mode the compose containers run
        # in — so generate real ones, same as SM_SECRET_KEY.
        secret_keys += [
            "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
            "SM_USERS_VERIFICATION_TOKEN_SECRET",
        ]
    db_name = to_snake_case(name)
    env_path = target / ".env.example"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    for key in secret_keys:
        env_text = comment_out_env_key(env_text, key)
    local_overrides: dict[str, str] = {}
    if db == "postgres":
        # The compose `postgres` service takes its password from .env, and
        # the dev SM_DATABASE_URL must match it (GH #444).
        env_text = add_postgres_password_placeholder(env_text)
        password = _secrets.token_urlsafe(24)
        local_overrides = {
            "POSTGRES_PASSWORD": password,
            "SM_DATABASE_URL": _db_url(db, db_name, flat=flat, password=password),
        }
    env_text = set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, db_name, flat=flat))
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

    scaffold_docker_assets(target, ctx, flat=flat)
    # Last, so .env picks up every key the recipes added to .env.example.
    write_local_env(target, secret_keys=secret_keys, overrides=local_overrides)

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
    # The sample lives inside the workspace, so it gets no per-module .github/:
    # GitHub only reads workflows from the repo root, where the template's
    # .github/ would be dead anyway. See GH #210.
    create_module(
        sample_dest,
        name=_SAMPLE_MODULE_NAME,
        framework_version=_FRAMEWORK_VERSION,
        standalone=False,
    )
    _seed_static_dist_placeholder(sample_dest / _SAMPLE_MODULE_NAME / "static" / "dist")


def _seed_static_dist_placeholder(static_dist: Path) -> None:
    # Hatch's force-include resolves at build time even for editable installs;
    # an empty placeholder keeps `uv sync` from failing before vite build runs.
    static_dist.mkdir(parents=True, exist_ok=True)
    (static_dist / ".gitkeep").touch()
