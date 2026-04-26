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
import logging
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from simple_module.case import to_kebab_case, to_pascal_case, to_snake_case

from simple_module_hosting.app_project import create_app_project as create_app_project
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

    display_name = to_pascal_case(name)
    slug = to_kebab_case(name)
    package_name = to_snake_case(name)

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
