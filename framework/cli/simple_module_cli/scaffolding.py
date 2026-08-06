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

import logging
import shutil
from collections.abc import Sequence
from pathlib import Path

# The template engine lives in _templating.py; the private names are imported
# here because long-standing tests monkeypatch them on this module.
from simple_module_cli._templating import (
    _PACKAGE_PATH_TOKEN,
    _apply_template_files,
    _require_empty_dest,
    _resolve_template_root,
)
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
    "is_inside_existing_repo",
    "pin_framework_deps",
    "resolve_framework_version",
]

logger = logging.getLogger(__name__)

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


def is_inside_existing_repo(dest: Path) -> bool:
    """Return True when ``dest`` lands inside an existing repo / host project.

    A module scaffolded under an existing host application (the documented
    monorepo ``modules/*`` layout) is an *in-repo* module: GitHub only runs
    workflows from the repository-root ``.github/workflows/``, so a per-module
    ``.github/`` is dead weight there — and the bundled ``publish.yml`` (which
    publishes ``simple_module_<name>`` to PyPI on any ``v*`` tag) is a footgun if
    it ever surfaces at the repo root. We detect this by walking up from
    ``dest``'s parent for a ``.git`` directory or a ``pyproject.toml`` (an
    existing repo / host / workspace member).

    ``dest`` itself is *excluded* from the walk — the module's own scaffolded
    ``pyproject.toml`` must not count as "an existing host". A truly standalone
    target (no repo/pyproject above it) returns False. See GH #210.
    """
    # ``resolve()`` allows ``dest`` to not exist yet; the walk is over its
    # absolute parents so a relative ``--dest`` is handled the same way.
    start = Path(dest).resolve().parent
    for parent in (start, *start.parents):
        if (parent / ".git").exists() or (parent / "pyproject.toml").is_file():
            return True
    return False


def _should_pin_framework_version(version: str | None) -> bool:
    """Whether ``version`` is a concrete pin rather than a skip sentinel.

    Both scaffolders skip pinning for ``None`` (a library caller that wants the
    template's ranges kept verbatim) and ``"*"`` (the npm-wildcard default,
    which would otherwise render the invalid PEP 508 specifier ``==*``). One
    rule, so the two paths can't drift. See GH #195 / #206.
    """
    return bool(version) and version != "*"


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
    standalone: bool = True,
) -> Path:
    """Scaffold a module package at ``dest``.

    When ``framework_version`` is a concrete version, the template's
    forward-looking ``simple_module_*`` ranges are rewritten to an exact pin so
    the module resolves against that framework version (e.g. ``uv add`` into the
    workspace that created it). Left as ``None`` (or the ``"*"`` sentinel), the
    template's ranges are kept verbatim. See GH #195.

    When ``standalone`` is False, the scaffolded ``.github/`` (CI + PyPI publish
    workflows) is omitted. Those nested workflows never run inside an existing
    host repo (GitHub only reads the repo-root ``.github/``) and ``publish.yml``
    is a footgun there, so callers creating an *in-repo* module pass
    ``standalone=False``. See GH #210.

    ``standalone=True`` additionally overlays ``_optional/standalone/`` (npm
    devDependencies + a tsconfig that resolves ``@simple-module-py/ui`` from the
    repo's own ``node_modules``) so the module type-checks outside a workspace.
    """
    dest = Path(dest)
    existed_before = dest.exists()
    _require_empty_dest(dest)
    display_name = to_pascal_case(name)
    slug = to_kebab_case(name)
    package_name = to_snake_case(name)
    substitutions = {
        "{{MODULE_NAME}}": display_name,
        "{{MODULE_SLUG}}": slug,
        "{{PACKAGE_NAME}}": package_name,
        "{{PACKAGE_NAME_UPPER}}": package_name.upper(),
        # npm-side pin for @simple-module-py/* devDependencies; "*" when the
        # caller skips pinning (mirrors _should_pin_framework_version).
        "{{FRAMEWORK_VERSION}}": (
            framework_version
            if framework_version is not None and _should_pin_framework_version(framework_version)
            else "*"
        ),
    }
    try:
        base_root = _resolve_template_root("module", template_root)
        _apply_template_files(
            base_root,
            dest,
            substitutions=substitutions,
            path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
        )
        if standalone:
            # Overlay standalone-only JS configs over the workspace defaults
            # (the base pass skips _optional/; an explicit root iterates it —
            # same pattern as recipes.py).
            _apply_template_files(
                base_root / "_optional" / "standalone",
                dest,
                substitutions=substitutions,
                path_rewrites={_PACKAGE_PATH_TOKEN: package_name},
            )
        else:
            shutil.rmtree(dest / ".github", ignore_errors=True)
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
