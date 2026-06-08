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

from simple_module_cli.case import (
    to_kebab_case,
    to_pascal_case,
    to_snake_case,
    validate_scaffold_name,
)

# Re-exported so the scaffolders and their long-standing callers keep importing
# version pinning from one place; the implementations live in pins.py.
from simple_module_cli.pins import pin_framework_deps, resolve_framework_version

__all__ = [
    "SAFE_PRESERVED_NAMES",
    "create_host",
    "create_module",
    "create_workspace",
    "pin_framework_deps",
    "resolve_framework_version",
]

logger = logging.getLogger(__name__)

_TEMPLATES_PACKAGE = "simple_module_cli.templates"
_PACKAGE_PATH_TOKEN = "__PACKAGE__"

# Pre-existing entries we tolerate at a scaffold target — typical leftovers
# from ``git init`` / ``gh repo create`` / IDE setup.
SAFE_PRESERVED_NAMES = frozenset(
    {".git", ".gitignore", ".gitattributes", ".editorconfig", ".DS_Store"}
    | {".claude", ".vscode", ".idea"}
    | {"README", "README.md", "README.rst"}
    | {"LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"}
    | {"CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md"}
)


def _module_to_pypi_name(name: str) -> str:
    return f"simple_module_{name.lower()}"


def _should_pin_framework_version(version: str | None) -> bool:
    """Whether ``version`` is a concrete pin rather than a skip sentinel.

    Both scaffolders skip pinning for ``None`` (a library caller that wants the
    template's ranges kept verbatim) and ``"*"`` (the npm-wildcard default,
    which would otherwise render the invalid PEP 508 specifier ``==*``). One
    rule, so the two paths can't drift. See GH #195 / #206.
    """
    return bool(version) and version != "*"


def _iter_template_files(template_root: Path):
    """Yield every file under ``template_root``. Skips ``_optional/`` paths."""
    for path in template_root.rglob("*"):
        if not path.is_file():
            continue
        if "_optional" in path.relative_to(template_root).parts:
            continue
        yield path


def _require_empty_dest(dest: Path, *, preserve_existing: frozenset[str] = frozenset()) -> None:
    """Refuse a non-empty destination unless every top-level entry is allowed.

    ``preserve_existing`` is matched against the *name* of each top-level entry,
    so callers can permit common pre-existing files (``.git``, ``README.md``,
    ...) without silently overwriting unrelated user content.
    """
    if dest.exists():
        unexpected = sorted(p.name for p in dest.iterdir() if p.name not in preserve_existing)
        if unexpected:
            raise FileExistsError(
                f"Destination {dest} exists and contains files that would collide "
                f"with the scaffold: {', '.join(unexpected)}. "
                "Move them aside or choose another path."
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
    preserve_existing: frozenset[str] = frozenset(),
) -> list[Path]:
    """Write template files into ``dest``; return paths skipped to preserve the user's copy."""
    preserved: list[Path] = []
    for src in _iter_template_files(src_root):
        rel_str = str(src.relative_to(src_root))
        for old, new in (path_rewrites or {}).items():
            rel_str = rel_str.replace(old, new)
        rel_str = rel_str.removesuffix(".tpl")
        target = dest / rel_str
        top = Path(rel_str).parts[0] if rel_str else ""
        if top in preserve_existing and target.exists():
            preserved.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".tpl":
            text = src.read_text(encoding="utf-8")
            for placeholder, value in substitutions.items():
                text = text.replace(placeholder, value)
            target.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, target)
    return preserved


def create_workspace(
    dest: Path,
    name: str,
    template_root: Path | None = None,
    framework_version: str = "*",
    *,
    preserve_existing: frozenset[str] = frozenset(),
) -> list[Path]:
    """Materialize the workspace-root shell at ``dest``; return preserved paths.

    Lays down the top-level ``pyproject.toml`` (uv workspace + dev tooling for
    ``make test``/``lint``), ``package.json`` (npm workspace), ``Makefile``
    (delegates to host), ``.env.example``, ``.gitignore``, and ``README.md``.
    Does NOT create the host or any modules — those go under ``dest/host`` and
    ``dest/modules/`` afterwards.

    ``framework_version`` pins ``simple_module_test`` in the root dev group;
    defaults to ``"*"`` for callers that don't need an exact pin.

    ``preserve_existing`` lists top-level entry names that may already exist
    in ``dest``; the scaffold's copy is skipped and the preserved path is
    included in the returned list. Other pre-existing entries raise
    ``FileExistsError``.
    """
    dest = Path(dest)
    _require_empty_dest(dest, preserve_existing=preserve_existing)
    preserved = _apply_template_files(
        _resolve_template_root("workspace", template_root),
        dest,
        {
            "{{HOST_NAME}}": validate_scaffold_name(name),
            "{{HOST_PYPI_NAME}}": to_kebab_case(name),
            "{{FRAMEWORK_VERSION}}": framework_version,
        },
        preserve_existing=preserve_existing,
    )
    logger.info("Scaffolded workspace root at %s", dest)
    return preserved


def create_host(
    dest: Path,
    name: str,
    modules: Sequence[str],
    template_root: Path | None = None,
    framework_version: str = "*",
    *,
    preserve_existing: frozenset[str] = frozenset(),
) -> list[Path]:
    """Scaffold a host project at ``dest``; return preserved pre-existing paths.

    ``preserve_existing`` semantics match :func:`create_workspace`.
    """
    dest = Path(dest)
    _require_empty_dest(dest, preserve_existing=preserve_existing)
    module_dep_lines = "\n".join(f'    "{_module_to_pypi_name(m)}>=0.1,<1.0",' for m in modules)
    preserved = _apply_template_files(
        _resolve_template_root("host", template_root),
        dest,
        {
            "{{HOST_NAME}}": validate_scaffold_name(name),
            "{{HOST_PYPI_NAME}}": to_kebab_case(name),
            "{{MODULE_DEPS}}": module_dep_lines,
            "{{FRAMEWORK_VERSION}}": framework_version,
        },
        preserve_existing=preserve_existing,
    )
    # Pin every simple_module_* host dep (framework packages *and* selected
    # bundled modules) to the lockstep version so the host's first `uv sync`
    # resolves — the template's >=1.0,<2.0 / >=0.1,<1.0 ranges match nothing
    # against pre-1.0 dists. See GH #206.
    if _should_pin_framework_version(framework_version):
        pin_framework_deps(dest / "pyproject.toml", framework_version)
    logger.info(
        "Scaffolded host '%s' at %s (modules: %s)", name, dest, ", ".join(modules) or "<none>"
    )
    return preserved


def create_module(
    dest: Path,
    name: str,
    template_root: Path | None = None,
    *,
    framework_version: str | None = None,
) -> Path:
    """Scaffold a module package at ``dest``.

    When ``framework_version`` is a concrete version, the template's
    forward-looking ``simple_module_*`` ranges are rewritten to an exact pin so
    the module resolves against that framework version (e.g. ``uv add`` into the
    workspace that created it). Left as ``None`` (or the ``"*"`` sentinel), the
    template's ranges are kept verbatim. See GH #195.
    """
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
        if _should_pin_framework_version(framework_version):
            pin_framework_deps(dest / "pyproject.toml", framework_version)
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
