"""Shared plumbing for ``smpy module`` commands.

Out-of-tree module repos have no frontend toolchain of their own — the
commands borrow one by scaffolding a throwaway host (via the same templates
as ``smpy create-host``) into ``.smpy/verify-host/`` and caching it there.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

import typer

from simple_module_cli.scaffolding import create_host, resolve_framework_version

VERIFY_HOST_RELPATH = Path(".smpy") / "verify-host"


@dataclass(frozen=True)
class ModuleInfo:
    """Identity of the module under the cwd, read from its pyproject."""

    root: Path
    pypi_name: str  # [project].name, e.g. simple_module_my_feature
    package_name: str  # the simple_module entry-point key, e.g. my_feature


def read_module_info(root: Path) -> ModuleInfo:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        typer.echo(f"error: no pyproject.toml in {root} — run from the module repo root.", err=True)
        raise typer.Exit(code=1)
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    entry_points = data.get("project", {}).get("entry-points", {}).get("simple_module", {})
    if not entry_points:
        typer.echo(
            "error: pyproject.toml declares no [project.entry-points.simple_module] — "
            "this does not look like a SimpleModule module.",
            err=True,
        )
        raise typer.Exit(code=1)
    return ModuleInfo(
        root=root,
        pypi_name=data["project"]["name"],
        package_name=next(iter(entry_points)),
    )


def require_binary(name: str) -> str:
    """Resolve ``name`` on PATH or exit with a clear message (npm on Windows is npm.cmd)."""
    path = shutil.which(name)
    if path is None:
        typer.echo(f"error: '{name}' not found on PATH — install it and retry.", err=True)
        raise typer.Exit(code=1)
    return path


def ensure_verify_host(info: ModuleInfo, *, fresh: bool = False) -> Path:
    """Scaffold (or reuse) the cached verify host; return its directory."""
    host_dir = info.root / VERIFY_HOST_RELPATH
    if fresh and host_dir.exists():
        shutil.rmtree(host_dir)
    if not (host_dir / "pyproject.toml").is_file():
        create_host(
            host_dir,
            name="verify_host",
            modules=[],
            framework_version=resolve_framework_version(),
        )
        _wire_module_dep(host_dir / "pyproject.toml", info.pypi_name)
    return host_dir


def _wire_module_dep(pyproject_path: Path, pypi_name: str) -> None:
    """Add the module as an editable path dependency of the verify host."""
    text = pyproject_path.read_text(encoding="utf-8")
    # Unpinned on purpose: [tool.uv.sources] overrides it with the local path.
    # Note: pin_framework_deps may have rewritten the array onto one line, so
    # match the opening bracket only — TOML tolerates the injected newline.
    text = text.replace("dependencies = [", f'dependencies = [\n    "{pypi_name}",', 1)
    text += f'\n[tool.uv.sources]\n{pypi_name} = {{ path = "../..", editable = true }}\n'
    pyproject_path.write_text(text, encoding="utf-8")
