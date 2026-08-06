"""``smpy module build`` — bundle ``<pkg>/assets_src/`` into ``<pkg>/static/dist/``.

Only for assets served via :meth:`ModuleBase.static_mounts` (vendor JS,
widgets, images). Inertia pages do NOT need this — the consuming host's Vite
build compiles ``pages/*.tsx`` straight from the wheel.

The module repo carries no bundler of its own: we borrow the verify host's
node toolchain (``.smpy/verify-host/client_app``) and point Vite at a
generated lib-mode config.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from simple_module_cli._module_host import ModuleInfo, ensure_verify_host, require_binary
from simple_module_cli.case import to_pascal_case

_ENTRY_CANDIDATES = ("index.ts", "index.tsx", "index.js")


def run_build(info: ModuleInfo, *, fresh: bool = False, runner=subprocess.run) -> None:
    assets_src = info.root / info.package_name / "assets_src"
    entry = next((assets_src / n for n in _ENTRY_CANDIDATES if (assets_src / n).is_file()), None)
    if entry is None:
        typer.echo(
            f"error: no {info.package_name}/assets_src/index.(ts|tsx|js) found. "
            "`smpy module build` bundles static_mounts() assets only — Inertia pages "
            "are built by the consuming host and need no bundling.",
            err=True,
        )
        raise typer.Exit(code=1)

    host = ensure_verify_host(info, fresh=fresh)
    client_app = host / "client_app"
    npm = require_binary("npm")
    if not (client_app / "node_modules").is_dir():
        typer.echo("[build] npm install (first run)")
        if runner([npm, "install"], cwd=client_app).returncode != 0:
            typer.echo("[build] FAILED at: npm install", err=True)
            raise typer.Exit(code=1)

    out_dir = info.root / info.package_name / "static" / "dist"
    config_path = info.root / ".smpy" / "module-build.config.mjs"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _vite_lib_config(entry, out_dir, global_name=to_pascal_case(info.package_name)),
        encoding="utf-8",
    )
    typer.echo(f"[build] vite build -> {info.package_name}/static/dist")
    npx = require_binary("npx")
    if runner([npx, "vite", "build", "--config", str(config_path)], cwd=client_app).returncode != 0:
        typer.echo("[build] FAILED at: vite build", err=True)
        raise typer.Exit(code=1)

    _warn_missing_force_include(info)
    typer.echo("[build] OK")


def _vite_lib_config(entry: Path, out_dir: Path, *, global_name: str) -> str:
    return f"""\
import {{ defineConfig }} from 'vite'

export default defineConfig({{
  build: {{
    lib: {{
      entry: {entry.as_posix()!r},
      formats: ['iife'],
      name: {global_name!r},
      fileName: () => 'index.js',
    }},
    outDir: {out_dir.as_posix()!r},
    emptyOutDir: true,
  }},
}})
"""


def _warn_missing_force_include(info: ModuleInfo) -> None:
    """static/dist is gitignored — without force-include the wheel silently omits it."""
    pyproject = (info.root / "pyproject.toml").read_text(encoding="utf-8")
    if f"{info.package_name}/static/dist" not in pyproject:
        typer.echo(
            "warning: pyproject.toml has no force-include for "
            f'"{info.package_name}/static/dist" — the built bundle will NOT ship in the wheel. '
            "Add under [tool.hatch.build.targets.wheel.force-include]:\n"
            f'  "{info.package_name}/static/dist" = "{info.package_name}/static/dist"',
            err=True,
        )
