"""PyPI and local-path sources for ``smpy add``."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from simple_module_cli._add_install import ExecRunner, _fail, post_install
from simple_module_cli.git_source import derive_range, scan_modules
from simple_module_cli.pyproject_edit import (
    save_pyproject,
    write_dependency,
    write_path_source,
    write_workspace_source,
)
from simple_module_cli.uv_workspace import is_workspace_member


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


def _resolve_local_path(project_dir: Path, spec_path: Path) -> tuple[Path, str]:
    """Resolve a local-path spec to ``(directory, text written to pyproject)``.

    A relative path is resolved against the ``--path`` project (the pyproject
    being edited, which is what ``[tool.uv.sources]`` paths are relative to).
    If nothing exists there but the path exists relative to the cwd, the cwd
    one is used and the written path is re-expressed relative to the project.
    """
    if spec_path.is_absolute():
        return spec_path, str(spec_path)
    root = project_dir / spec_path
    if not root.exists() and (Path.cwd() / spec_path).exists():
        root = Path.cwd() / spec_path
        return root, os.path.relpath(root.resolve(), project_dir.resolve())
    return root, str(spec_path)


def _add_path(
    doc, pyproject: Path, spec_path: Path, no_sync: bool, exec_runner: ExecRunner
) -> list[str]:
    root, written = _resolve_local_path(pyproject.parent, spec_path)
    found = [m for m in scan_modules(root) if m.subdirectory is None]
    if not found:
        raise _fail(
            f"{root} has no [project.entry-points.simple_module] entry point at its root "
            f"(relative paths resolve against the --path project, {pyproject.parent}, "
            "falling back to the current directory)"
        )
    mod = found[0]
    if is_workspace_member(pyproject.parent, root):
        # uv refuses a path source for a workspace member; the scaffold's own
        # sample module is wired the same way (unpinned + workspace = true).
        write_dependency(doc, mod.dist_name, "")
        write_workspace_source(doc, mod.dist_name)
        typer.echo(f"Added {mod.dist_name} (uv workspace member {written}).")
    else:
        write_dependency(doc, mod.dist_name, derive_range(mod.version))
        write_path_source(doc, mod.dist_name, path=written)
        typer.echo(f"Added {mod.dist_name} (editable path {written}).")
    save_pyproject(pyproject, doc)
    if not no_sync:
        post_install(
            pyproject.parent,
            [mod.dist_name],
            [mod.dist_name] if mod.ships_models else [],
            exec_runner,
        )
    return [mod.dist_name]
