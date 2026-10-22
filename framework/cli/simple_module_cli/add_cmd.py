"""``smpy add`` — add a module from PyPI, any git repo, or a local path.

Git specs: ``git+<url>[@<tag|branch|sha>][#subdirectory=<dir>]``. The spec
is resolved first (ls-remote + shallow clone + entry-point scan); the host
pyproject is written only after resolution succeeds. A git spec without
``#subdirectory`` is scanned for module packages — one match is added
directly, several go through ``--module``/``--all`` or an interactive
picker. Then: ``uv sync`` → ``smpy host gen-pages`` → ``smpy host
sync-js-deps`` → entry-point verification, unless ``--no-sync``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli._add_install import (
    ExecRunner,
    _default_exec_runner,
    _fail,
    post_install,
)
from simple_module_cli._add_sources import _add_path, _add_pypi
from simple_module_cli.git_source import (
    FoundModule,
    SpecError,
    classify_ref,
    derive_range,
    parse_add_spec,
    scan_modules,
    shallow_clone,
)
from simple_module_cli.pyproject_edit import (
    has_git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
    write_git_source,
)

__all__ = ["ExecRunner", "add_module", "post_install", "run_add"]

_SECURITY_NOTICE = (
    "note: this installs and runs code from a URL you chose — review the "
    "repository before booting the host."
)


def _choose(
    found: list[FoundModule],
    *,
    select: list[str] | None,
    all_modules: bool,
    assume_yes: bool,
) -> list[FoundModule]:
    if len(found) == 1:
        return found
    if all_modules:
        return found
    if select:
        wanted = {s.replace("-", "_").lower() for s in select}
        chosen = [m for m in found if m.dist_name.replace("-", "_").lower() in wanted]
        missing = wanted - {m.dist_name.replace("-", "_").lower() for m in chosen}
        if missing:
            raise _fail(f"module(s) not found in repo: {', '.join(sorted(missing))}")
        return chosen
    if assume_yes:
        names = ", ".join(m.dist_name for m in found)
        raise _fail(f"repo contains multiple modules ({names}); pick with --module a,b or --all")
    return [
        m
        for m in found
        if typer.confirm(f"Include {m.dist_name} ({m.subdirectory or 'repo root'})?")
    ]


def run_add(
    spec: str,
    *,
    pyproject: Path,
    select: list[str] | None = None,
    all_modules: bool = False,
    no_sync: bool = False,
    assume_yes: bool = False,
    git_runner=None,
    exec_runner: ExecRunner | None = None,
) -> list[str]:
    if not pyproject.is_file():
        raise _fail(f"{pyproject} not found")
    exec_runner = exec_runner or _default_exec_runner
    try:
        parsed = parse_add_spec(spec)
    except SpecError as exc:
        raise _fail(str(exc)) from exc
    doc = load_pyproject(pyproject)

    if parsed.kind == "pypi":
        return _add_pypi(doc, pyproject, parsed.raw, no_sync, exec_runner)
    if parsed.kind == "path":
        assert parsed.path is not None
        return _add_path(doc, pyproject, parsed.path, no_sync, exec_runner)

    assert parsed.git is not None
    git_kwargs = {"run": git_runner} if git_runner else {}
    ref_info = classify_ref(parsed.git.url, parsed.git.ref, **git_kwargs)
    with tempfile.TemporaryDirectory(prefix="smpy-add-") as tmp:
        clone = shallow_clone(parsed.git.url, ref_info, Path(tmp) / "repo", **git_kwargs)
        found = scan_modules(clone)
    if parsed.git.subdirectory is not None:
        found = [m for m in found if m.subdirectory == parsed.git.subdirectory]
    if not found:
        where = (
            f"subdirectory {parsed.git.subdirectory!r} of {parsed.git.url}"
            if parsed.git.subdirectory
            else parsed.git.url
        )
        raise _fail(f"{where} has no package declaring [project.entry-points.simple_module]")
    chosen = _choose(found, select=select, all_modules=all_modules, assume_yes=assume_yes)
    if not chosen:
        raise _fail("no modules selected")

    if not has_git_sources(doc):
        typer.echo(_SECURITY_NOTICE)
    for mod in chosen:
        write_dependency(doc, mod.dist_name, derive_range(mod.version))
        write_git_source(
            doc,
            mod.dist_name,
            url=parsed.git.url,
            ref_info=ref_info,
            subdirectory=mod.subdirectory,
        )
        pin = f"{ref_info.kind} {ref_info.value}" if ref_info.value else "default branch"
        typer.echo(f"Added {mod.dist_name} {mod.version} from git ({pin}).")
        if ref_info.kind == "branch":
            typer.echo(
                f"  {mod.dist_name} tracks a branch — dev-mode pin; prefer a v* tag for releases."
            )
    save_pyproject(pyproject, doc)
    if not no_sync:
        post_install(
            pyproject.parent,
            [m.dist_name for m in chosen],
            [m.dist_name for m in chosen if m.ships_models],
            exec_runner,
        )
    return [m.dist_name for m in chosen]


def add_module(
    spec: Annotated[
        str,
        typer.Argument(help="PyPI requirement, git+URL[@ref][#subdirectory=dir], or local path."),
    ],
    module: Annotated[
        str,
        typer.Option("--module", help="Comma-separated module dist names (multi-module repos)."),
    ] = "",
    all_modules: Annotated[
        bool, typer.Option("--all", help="Add every module found in the repo.")
    ] = False,
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Write pyproject only; skip uv sync / gen-pages."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Never prompt (fail instead).")] = False,
) -> None:
    """Add a module dependency from PyPI, a git repo, or a local path."""
    pyproject = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    select = [m.strip() for m in module.split(",") if m.strip()]
    run_add(
        spec,
        pyproject=pyproject,
        select=select or None,
        all_modules=all_modules,
        no_sync=no_sync,
        assume_yes=yes,
    )
