"""Host + module scaffolding via package-data templates.

* :func:`create_host` materializes a new host project from the templates
  under ``simple_module_hosting/templates/host/``.
* :func:`create_module` materializes a new module package from
  ``simple_module_hosting/templates/module/``.

The frontend pages manifest + per-module JS dep discovery used to live
here as well; both moved to :mod:`simple_module_hosting.manifest` to
keep this file under the project's per-file line cap. They're re-exported
below so existing import sites keep working.
"""

from __future__ import annotations

import importlib.resources
import json as _json
import logging
import re
import secrets as _secrets
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    compute_module_pages,
    read_module_package_json,
    repo_root_from_client_app,
    write_module_pages_manifest,
)

__all__ = [
    "collect_module_js_deps",
    "compute_module_pages",
    "create_app_project",
    "create_host",
    "create_module",
    "read_module_package_json",
    "repo_root_from_client_app",
    "write_module_pages_manifest",
]

logger = logging.getLogger(__name__)

# Templates ship as package data under simple_module_hosting/templates/{host,module}/.
_TEMPLATES_PACKAGE = "simple_module_hosting.templates"

# Path-segment substitution token used by create_module.
_PACKAGE_PATH_TOKEN = "__PACKAGE__"


def _module_to_pypi_name(name: str) -> str:
    """'Products' -> 'simple_module_products'. Matches the publishing convention."""
    return f"simple_module_{name.lower()}"


def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``, preserving relative paths.

    Skips any path under an ``_optional/`` segment — those are recipe-managed
    templates consumed by :mod:`simple_module_hosting.cli.recipes`, not by
    the default scaffolding pass.
    """
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path


def _require_empty_dest(dest: Path) -> None:
    """Raise if ``dest`` is an existing non-empty directory — never clobber files."""
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(
            f"Destination {dest} already exists and is non-empty. "
            "Choose a new path or remove the contents first."
        )
    dest.mkdir(parents=True, exist_ok=True)


def _resolve_template_root(subdir: str, override: Path | None) -> Path:
    """Return the scaffold template root, either from package data or an override."""
    if override is not None:
        return Path(override)
    return Path(str(importlib.resources.files(_TEMPLATES_PACKAGE) / subdir))


def _apply_template_files(
    src_root: Path,
    dest: Path,
    substitutions: Mapping[str, str],
    *,
    path_rewrites: Mapping[str, str] | None = None,
) -> None:
    """Copy every file under ``src_root`` to ``dest``, applying substitutions.

    Files ending in ``.tpl`` are read as text, placeholders replaced, and
    written without the suffix. Every other file is copied verbatim. If
    ``path_rewrites`` is given, each key is replaced by its value anywhere
    in relative paths (used by :func:`create_module` to rename the
    ``__PACKAGE__`` directory placeholder).
    """
    for src in _iter_template_files(src_root):
        rel_str = str(src.relative_to(src_root))
        for old, new in (path_rewrites or {}).items():
            rel_str = rel_str.replace(old, new)
        rel_str = rel_str.removesuffix(".tpl")
        target = dest / rel_str
        target.parent.mkdir(parents=True, exist_ok=True)

        if src.suffix == ".tpl":
            text = src.read_text(encoding="utf-8")
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, target)


def create_host(
    dest: Path,
    name: str,
    modules: Sequence[str],
    template_root: Path | None = None,
) -> Path:
    """Materialize a SimpleModule host scaffold at ``dest``.

    Modules listed in ``modules`` become PyPI dependencies in the scaffolded
    ``pyproject.toml`` (e.g. ``"simple_module_products>=0.1,<1.0"``). Raises
    :class:`FileExistsError` if ``dest`` is an existing non-empty directory.
    """
    dest = Path(dest)
    _require_empty_dest(dest)

    module_dep_lines = "\n".join(f'    "{_module_to_pypi_name(m)}>=0.1,<1.0",' for m in modules)
    _apply_template_files(
        _resolve_template_root("host", template_root),
        dest,
        {"{{HOST_NAME}}": name, "{{MODULE_DEPS}}": module_dep_lines},
    )

    logger.info(
        "Scaffolded host '%s' at %s (modules: %s)", name, dest, ", ".join(modules) or "<none>"
    )
    return dest


def _to_snake_case(name: str) -> str:
    """'MyFeature' / 'my-feature' / 'My Feature' -> 'my_feature'."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    s = re.sub(r"[\s\-]+", "_", s)
    return s.lower()


def _to_kebab_case(name: str) -> str:
    """'MyFeature' / 'my_feature' -> 'my-feature' (used as the PyPI slug)."""
    return _to_snake_case(name).replace("_", "-")


def _to_pascal_case(name: str) -> str:
    """'my-feature' / 'my_feature' -> 'MyFeature' (the display name in Meta)."""
    snake = _to_snake_case(name)
    return "".join(part.capitalize() for part in snake.split("_") if part)


def create_module(
    dest: Path,
    name: str,
    template_root: Path | None = None,
) -> Path:
    """Materialize a publishable module package at ``dest``.

    ``name`` is accepted in any case style (``MyFeature``, ``my-feature``,
    ``my_feature``) and normalized to three forms:

    * ``MODULE_NAME``  — ``PascalCase``, appears in ``Meta(name=...)``
    * ``MODULE_SLUG``  — ``kebab-case``, used in the PyPI distribution name
    * ``PACKAGE_NAME`` — ``snake_case``, the importable Python package and
      the entry_point key
    """
    dest = Path(dest)
    _require_empty_dest(dest)

    display_name = _to_pascal_case(name)
    slug = _to_kebab_case(name)
    package_name = _to_snake_case(name)

    _apply_template_files(
        _resolve_template_root("module", template_root),
        dest,
        substitutions={
            "{{MODULE_NAME}}": display_name,
            "{{MODULE_SLUG}}": slug,
            "{{PACKAGE_NAME}}": package_name,
        },
        path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
    )

    logger.info("Scaffolded module '%s' at %s (package: %s)", display_name, dest, package_name)
    return dest


# ---------------------------------------------------------------
# create_app_project — used by `sm new` / `simple-module new`
# ---------------------------------------------------------------

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
    # Imports are local to avoid a circular import: cli.recipes is allowed
    # to import from scaffolding in the future, but scaffolding itself
    # only needs catalog/recipes at call time.
    from simple_module_hosting.cli.catalog import CATALOG, PRESETS, expand_deps
    from simple_module_hosting.cli.recipes import RECIPES, ScaffoldCtx

    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            f"Destination {target} already exists and is non-empty; "
            "choose a new path or remove its contents first."
        )

    chosen = list(selected) if selected is not None else list(PRESETS["standard"])
    resolved, _added = expand_deps(chosen)

    display_names = [CATALOG[m].display.replace(" ", "") for m in resolved]
    create_host(target, name=name, modules=display_names)

    py_deps = [f"simple_module_hosting=={_FRAMEWORK_VERSION}"] + [
        f"{CATALOG[m].package}=={_FRAMEWORK_VERSION}" for m in resolved
    ]

    env_path = target / ".env.example"
    env_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    env_text = _set_env_key(env_text, "SM_SECRET_KEY", _secrets.token_urlsafe(32))
    env_text = _set_env_key(env_text, "SM_DATABASE_URL", _db_url(db, _to_kebab_case(name)))
    env_text = _set_env_key(env_text, "SM_MULTI_TENANT", "true" if tenancy else "false")
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
        data = {"name": _to_kebab_case(name), "private": True, "type": "module"}
    data.setdefault("dependencies", {}).update(_APP_NPM_DEPS)
    data.setdefault("devDependencies", {}).update(_APP_NPM_DEV_DEPS)
    pkg_path.write_text(_json.dumps(data, indent=2) + "\n", encoding="utf-8")

    ctx = ScaffoldCtx(name=name, db=db, tenancy=tenancy, selected=tuple(resolved))
    for mod_name in resolved:
        recipe_key = CATALOG[mod_name].recipe
        if recipe_key is not None and recipe_key in RECIPES:
            RECIPES[recipe_key].apply(target, ctx)


def _set_env_key(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    prefix = f"{key}="
    out = [ln for ln in lines if not ln.startswith(prefix)]
    out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


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
