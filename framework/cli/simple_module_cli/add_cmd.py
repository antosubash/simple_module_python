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

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

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
    write_path_source,
)

__all__ = ["ExecRunner", "add_module", "post_install", "run_add"]

ExecRunner = Callable[[list[str], Path], int]

_SECURITY_NOTICE = (
    "note: this installs and runs code from a URL you chose — review the "
    "repository before booting the host."
)

_ENTRYPOINT_CHECK = (
    "import sys\n"
    "from importlib.metadata import distributions\n"
    "target = sys.argv[1].replace('-', '_').lower()\n"
    "for dist in distributions():\n"
    "    if any(ep.group == 'simple_module' for ep in dist.entry_points):\n"
    "        name = (dist.metadata['Name'] or '').replace('-', '_').lower()\n"
    "        if name == target:\n"
    "            sys.exit(0)\n"
    "sys.exit(1)\n"
)


def _default_exec_runner(cmd: list[str], cwd: Path) -> int:
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _fail(message: str) -> typer.Exit:
    typer.echo(f"ERROR: {message}", err=True)
    return typer.Exit(code=1)


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


def post_install(
    project_dir: Path,
    dists: list[str],
    models_dists: list[str],
    exec_runner: ExecRunner,
) -> None:
    """uv sync → gen-pages → sync-js-deps → entry-point check → reminders."""
    if exec_runner(["uv", "sync"], project_dir) != 0:
        raise _fail("`uv sync` failed — pyproject was written; fix and re-run `uv sync`.")
    if (project_dir / "client_app").is_dir():
        exec_runner(["uv", "run", "smpy", "host", "gen-pages"], project_dir)
        exec_runner(["uv", "run", "smpy", "host", "sync-js-deps"], project_dir)
    for dist in dists:
        code = exec_runner(["uv", "run", "python", "-c", _ENTRYPOINT_CHECK, dist], project_dir)
        if code != 0:
            raise _fail(
                f"{dist} installed but exposes no [project.entry-points.simple_module] "
                "entry point — it is not a SimpleModule module."
            )
    for dist in models_dists:
        typer.echo(
            f"{dist} ships database models — generate and apply the migration:\n"
            f'  make migration msg="add {dist}"\n  make migrate'
        )


def _add_pypi(doc, pyproject: Path, raw: str, no_sync: bool, exec_runner: ExecRunner) -> list[str]:
    name = raw
    for i, ch in enumerate(raw):
        if ch in "<>=!~[; ":
            name = raw[:i]
            break
    constraint = raw[len(name) :]
    write_dependency(doc, name, constraint)
    save_pyproject(pyproject, doc)
    typer.echo(f"Added {name} (PyPI).")
    if not no_sync:
        post_install(pyproject.parent, [name], [], exec_runner)
    return [name]


def _add_path(
    doc, pyproject: Path, spec_path: Path, no_sync: bool, exec_runner: ExecRunner
) -> list[str]:
    root = spec_path if spec_path.is_absolute() else pyproject.parent / spec_path
    found = [m for m in scan_modules(root) if m.subdirectory is None]
    if not found:
        raise _fail(f"{root} has no [project.entry-points.simple_module] entry point at its root")
    mod = found[0]
    write_dependency(doc, mod.dist_name, derive_range(mod.version))
    write_path_source(doc, mod.dist_name, path=str(spec_path))
    save_pyproject(pyproject, doc)
    typer.echo(f"Added {mod.dist_name} (editable path {spec_path}).")
    if not no_sync:
        post_install(
            pyproject.parent,
            [mod.dist_name],
            [mod.dist_name] if mod.ships_models else [],
            exec_runner,
        )
    return [mod.dist_name]


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
