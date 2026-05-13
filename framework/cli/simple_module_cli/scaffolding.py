"""Host + module scaffolding via package-data templates.

* :func:`create_workspace` materializes the project-root workspace shell
  (top-level ``pyproject.toml`` / ``package.json`` / ``Makefile``) from
  ``simple_module_cli/templates/workspace/``.
* :func:`create_host` materializes a new host project from the templates
  under ``simple_module_cli/templates/host/``.
* :func:`create_module` materializes a new module package from
  ``simple_module_cli/templates/module/``.

The frontend pages manifest + per-module JS dep discovery live in
:mod:`simple_module_hosting.manifest` (those need module-discovery and
stay in hosting).
"""

from __future__ import annotations

import importlib.resources
import logging
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

from simple_module_cli.case import to_kebab_case, to_pascal_case, to_snake_case

__all__ = ["create_host", "create_module", "create_workspace"]

logger = logging.getLogger(__name__)

_TEMPLATES_PACKAGE = "simple_module_cli.templates"
_PACKAGE_PATH_TOKEN = "__PACKAGE__"


def _module_to_pypi_name(name: str) -> str:
    return f"simple_module_{name.lower()}"


def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``. Skips ``_optional/`` paths."""
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path


def _require_empty_dest(dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(
            f"Destination {dest} already exists and is non-empty. "
            "Choose a new path or remove the contents first."
        )
    dest.mkdir(parents=True, exist_ok=True)


def _resolve_template_root(subdir: str, override: Path | None) -> Path:
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


def create_workspace(
    dest: Path,
    name: str,
    template_root: Path | None = None,
) -> Path:
    """Materialize the workspace-root shell at ``dest``.

    Lays down the top-level ``pyproject.toml`` (uv workspace), ``package.json``
    (npm workspace), ``Makefile`` (delegates to host), ``.env.example``,
    ``.gitignore``, and ``README.md``. Does NOT create the host or any
    modules — those go under ``dest/host`` and ``dest/modules/`` afterwards.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _apply_template_files(
        _resolve_template_root("workspace", template_root),
        dest,
        {"{{HOST_NAME}}": to_kebab_case(name)},
    )
    logger.info("Scaffolded workspace root at %s", dest)
    return dest


def create_host(
    dest: Path,
    name: str,
    modules: Sequence[str],
    template_root: Path | None = None,
    framework_version: str = "*",
) -> Path:
    dest = Path(dest)
    _require_empty_dest(dest)
    module_dep_lines = "\n".join(f'    "{_module_to_pypi_name(m)}>=0.1,<1.0",' for m in modules)
    _apply_template_files(
        _resolve_template_root("host", template_root),
        dest,
        {
            "{{HOST_NAME}}": name,
            "{{MODULE_DEPS}}": module_dep_lines,
            "{{FRAMEWORK_VERSION}}": framework_version,
        },
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
    dest = Path(dest)
    existed_before = dest.exists()
    _require_empty_dest(dest)
    display_name = to_pascal_case(name)
    slug = to_kebab_case(name)
    package_name = to_snake_case(name)
    try:
        _apply_template_files(
            _resolve_template_root("module", template_root),
            dest,
            substitutions={
                "{{MODULE_NAME}}": display_name,
                "{{MODULE_SLUG}}": slug,
                "{{PACKAGE_NAME}}": package_name,
                "{{PACKAGE_NAME_UPPER}}": package_name.upper(),
            },
            path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
        )
    except Exception:
        # Rollback so a half-scaffolded directory doesn't leave the user
        # with an unparseable Python package and the impression that a
        # retry won't work because ``dest`` is now non-empty. We only
        # nuke the directory we created — never one we found pre-existing.
        if not existed_before and dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        raise
    logger.info("Scaffolded module '%s' at %s (package: %s)", display_name, dest, package_name)
    return dest
