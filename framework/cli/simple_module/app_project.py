"""Greenfield ``simple-module new`` scaffolding.

Wraps :func:`simple_module_hosting.scaffolding.create_host` with the
opinionated bits — module-list resolution from the CLI catalog, secret
generation, DB URL selection, ``pyproject.toml`` / ``package.json``
rewriting, and post-scaffold recipe application.

Lives in its own module to keep ``scaffolding.py`` under the per-file
line cap and to make the surface area of "host scaffold" vs "app
scaffold" obvious to readers.
"""

from __future__ import annotations

import json as _json
import secrets as _secrets
from collections.abc import Sequence
from pathlib import Path

from simple_module._env import set_env_key
from simple_module.case import to_kebab_case, to_pascal_case
from simple_module.catalog import CATALOG, PRESETS, expand_deps
from simple_module.recipes import RECIPES, ScaffoldCtx
from simple_module.scaffolding import create_host

__all__ = ["create_app_project"]

_FRAMEWORK_VERSION = "0.0.1"

_APP_PY_DEV_DEPS = [f"simple_module_test=={_FRAMEWORK_VERSION}", "pytest>=8.0"]

_APP_NPM_DEPS = {
    "@simple-module-py/ui": _FRAMEWORK_VERSION,
    "@simple-module-py/i18n": _FRAMEWORK_VERSION,
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^1.0.0",
}
_APP_NPM_DEV_DEPS = {
    "@simple-module-py/tsconfig": _FRAMEWORK_VERSION,
    "@vitejs/plugin-react": "^5.0.0",
    "typescript": "^5.6.0",
    "vite": "^8.0.0",
}


def create_app_project(
    target: Path,
    *,
    name: str,
    db: str = "sqlite",
    tenancy: bool = False,
    selected: Sequence[str] | None = None,
) -> None:
    """Greenfield ``simple-module new`` scaffold.

    Wraps :func:`create_host` with a chosen module list (defaults to the
    ``standard`` preset), generates a secret, picks a DB URL, rewrites
    the generated ``package.json`` / ``pyproject.toml`` to pin exact
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
    create_host(target, name=name, modules=display_names)

    py_deps = [f"simple_module_hosting=={_FRAMEWORK_VERSION}"] + [
        f"{CATALOG[m].package}=={_FRAMEWORK_VERSION}" for m in resolved
    ]

    env_path = target / ".env.example"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    env_text = set_env_key(env_text, "SM_SECRET_KEY", _secrets.token_urlsafe(32))
    env_text = set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, to_kebab_case(name)))
    env_text = set_env_key(env_text, "SM_MULTI_TENANT", "true" if tenancy else "false")
    env_path.write_text(env_text, encoding="utf-8")

    pyproject = target / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8")
        text = _inject_py_deps(text, py_deps, _APP_PY_DEV_DEPS)
        pyproject.write_text(text, encoding="utf-8")

    pkg_path = target / "package.json"
    if pkg_path.exists():
        data = _json.loads(pkg_path.read_text(encoding="utf-8"))
    else:
        data = {"name": to_kebab_case(name), "private": True, "type": "module"}
    data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
    data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
    pkg_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")

    ctx = ScaffoldCtx(name=name, db=db, tenancy=tenancy, selected=tuple(resolved))
    for mod_name in resolved:
        recipe_key = CATALOG[mod_name].recipe
        if recipe_key is not None and recipe_key in RECIPES:
            RECIPES[recipe_key].apply(target, ctx)


def _db_url(db: str, slug: str) -> str:
    if db == "postgres":
        return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{slug}"
    return "sqlite+aiosqlite:///./app.db"


def _inject_py_deps(text: str, deps: list[str], dev_deps: list[str]) -> str:
    """Replace project.dependencies + dependency-groups.dev in a pyproject.toml."""
    import tomlkit

    doc = tomlkit.parse(text)
    project = doc.setdefault("project", tomlkit.table())
    project["dependencies"] = list(deps)
    groups = doc.setdefault("dependency-groups", tomlkit.table())
    groups["dev"] = list(dev_deps)
    return tomlkit.dumps(doc)
