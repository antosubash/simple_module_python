"""Resolve and pin the framework version that scaffolded apps depend on.

Kept separate from :mod:`simple_module_cli.scaffolding` (template
materialization) because version resolution + dependency pinning is its own
concern: the scaffolders, ``cli`` commands, and ``app_project`` all reach for
it independently. The module templates ship forward-looking ``simple_module_*``
ranges (``>=1.0,<2.0`` / ``>=0.1,<1.0``) against the framework's eventual stable
line, but the published distributions are pre-1.0 (``0.0.x``), so those ranges
resolve to nothing on PyPI. Rewriting them to an exact ``==`` pin lets a freshly
scaffolded app/module resolve against the framework version that created it.
See GH #195 / #206.
"""

from __future__ import annotations

from pathlib import Path


def resolve_framework_version() -> str:
    """Resolve the framework version that scaffolded apps should pin against.

    The CLI ships in lockstep with the rest of the framework (one
    ``bump_version.py`` rewrites every ``pyproject.toml``), so its own
    installed distribution version is the source of truth. Falls back to a
    placeholder for editable installs lacking dist-info — never reached from a
    release wheel.
    """
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        return pkg_version("simple_module_cli")
    except PackageNotFoundError:
        return "0.0.0"


def _pin_one(dep: str, version: str) -> str:
    """Pin a single ``simple_module_*`` requirement to ``==version``; else pass through."""
    pkg = dep.split(">=", 1)[0].split("==", 1)[0].split("<", 1)[0].strip()
    if pkg.startswith(("simple_module_", "simple-module-")):
        return f"{pkg}=={version}"
    return dep


def pin_framework_deps(pyproject_path: Path, version: str) -> None:
    """Pin every ``simple_module_*`` requirement in a pyproject to ``==version``.

    Rewrites both ``dependencies`` and every ``optional-dependencies`` extra
    (the module template's ``dev`` extra pins ``simple_module_test``). Used by
    ``create_module`` and ``create_host`` so a freshly scaffolded package
    resolves against the framework version that created it. See GH #195 / #206.
    """
    import tomlkit

    doc = tomlkit.parse(pyproject_path.read_text(encoding="utf-8"))
    project = doc.get("project")
    if project is None:
        return
    deps = project.get("dependencies")
    if deps is not None:
        project["dependencies"] = [_pin_one(dep, version) for dep in deps]
    optional = project.get("optional-dependencies")
    if optional is not None:
        for extra, items in list(optional.items()):
            optional[extra] = [_pin_one(dep, version) for dep in items]
    pyproject_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
