"""``sm host`` plugin — project-time helpers exposed through the simple-module CLI.

Commands here need module discovery (``simple_module_core.discover_modules``)
and the manifest helpers; they're not part of the standalone scaffolder.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from simple_module_core import discover_modules

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    repo_root_from_client_app,
    write_module_pages_manifest,
)

app = typer.Typer(
    help="Project-time helpers (frontend pages manifest, module JS dep sync).",
    no_args_is_help=True,
)


@app.command("gen-pages")
def gen_pages(
    host_dir: Annotated[
        Path,
        typer.Option(
            "--host-dir",
            help="Path to the host's client_app directory. Defaults to ./client_app.",
        ),
    ] = Path("client_app"),
) -> None:
    """Regenerate client_app/modules.{manifest.json,generated.ts,generated.css}."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_dir.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_dir}", err=True)
        raise typer.Exit(code=1)
    modules = discover_modules()
    written = write_module_pages_manifest(modules, host_dir)
    typer.echo(
        f"Wrote {written['manifest'].name}, {written['generated'].name}, "
        f"{written['css'].name} to {host_dir}"
    )


@app.command("sync-js-deps")
def sync_js_deps(
    host_client_app: Annotated[
        Path,
        typer.Option(
            "--host-client-app",
            help="Path to host/client_app. Defaults to ./client_app.",
        ),
    ] = Path("client_app"),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print the npm install command only.")
    ] = False,
) -> None:
    """Install JS deps declared by installed modules into host's node_modules."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_client_app.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_client_app}", err=True)
        raise typer.Exit(code=1)

    modules = discover_modules()
    by_module = collect_module_js_deps(modules)
    if not by_module:
        typer.echo("No module JS dependencies declared.")
        return

    specs: list[str] = []
    for mod_name in sorted(by_module):
        for dep, rng in sorted(by_module[mod_name].items()):
            specs.append(f"{dep}@{rng}")
    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            deduped.append(spec)

    npm = shutil.which("npm")
    if npm is None:
        typer.echo("ERROR: npm not found on PATH.", err=True)
        raise typer.Exit(code=1)

    repo_root = repo_root_from_client_app(host_client_app)
    try:
        workspace = str(host_client_app.resolve().relative_to(repo_root))
    except ValueError:
        workspace = str(host_client_app.resolve())

    cmd = [
        npm,
        "install",
        "--workspace",
        workspace,
        "--save=false",
        "--no-audit",
        "--no-fund",
        *deduped,
    ]
    typer.echo("Installing module JS deps:")
    for spec in deduped:
        typer.echo(f"  {spec}")
    if dry_run:
        typer.echo("(dry-run) " + " ".join(cmd))
        return
    result = subprocess.run(cmd, cwd=repo_root, check=False)
    raise typer.Exit(code=result.returncode)
