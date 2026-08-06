"""``smpy module`` — commands for developing a module out-of-tree (own repo)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer

from simple_module_cli._module_host import (
    ModuleInfo,
    ensure_verify_host,
    read_module_info,
    require_binary,
)

module_app = typer.Typer(help="Develop a SimpleModule module outside a host repo.")


def run_verify(info: ModuleInfo, *, fresh: bool = False, runner=subprocess.run) -> None:
    """Prove the module's TSX + CSS compile against a real scaffolded host.

    Output streams straight to the terminal (CI logs want the full Vite/tsc
    output); on failure we name the step and exit 1.
    """
    host = ensure_verify_host(info, fresh=fresh)
    client_app = host / "client_app"
    uv, npm = require_binary("uv"), require_binary("npm")
    steps: tuple[tuple[str, list[str], Path], ...] = (
        ("uv sync", [uv, "sync"], host),
        ("npm install", [npm, "install"], client_app),
        (
            "gen-pages",
            [
                uv,
                "run",
                "python",
                "-m",
                "simple_module_hosting",
                "gen-pages",
                "--host-dir=client_app",
            ],
            host,
        ),
        ("frontend build (tsc + vite)", [npm, "run", "build"], client_app),
    )
    for label, cmd, cwd in steps:
        typer.echo(f"[verify] {label}")
        if runner(cmd, cwd=cwd).returncode != 0:
            typer.echo(f"[verify] FAILED at: {label}", err=True)
            raise typer.Exit(code=1)
    typer.echo("[verify] OK — module frontend builds against a scaffolded host")


@module_app.command("verify")
def verify_command(
    fresh: bool = typer.Option(
        False, "--fresh", help="Rebuild the cached .smpy/verify-host from scratch."
    ),
) -> None:
    """Build this module's frontend inside a throwaway scaffolded host."""
    run_verify(read_module_info(Path.cwd()), fresh=fresh)
