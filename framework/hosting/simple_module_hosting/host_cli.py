"""``smpy host`` plugin — project-time helpers exposed through the simple-module CLI.

Commands here need module discovery (``simple_module_core.discover_modules``)
and the manifest helpers; they're not part of the standalone scaffolder.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from simple_module_core import discover_modules, resolve_auth_provider, select_auth_provider

from simple_module_hosting.manifest import (
    collect_module_js_deps,
    repo_root_from_client_app,
    write_module_pages_manifest,
)


def _declares_workspaces(root: Path) -> bool:
    """True when ``root/package.json`` is an npm workspace root."""
    try:
        return "workspaces" in json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False


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
    """Regenerate client_app/modules.{manifest.json,generated.ts,generated.css,assets.json}."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_dir.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_dir}", err=True)
        raise typer.Exit(code=1)
    # Skip the auth provider the host won't boot — its pages would otherwise
    # ship in the bundle with no view endpoint able to render them.
    modules = select_auth_provider(discover_modules(), resolve_auth_provider())
    try:
        written = write_module_pages_manifest(modules, host_dir)
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Module pages manifest: {len(modules)} module(s) "
        f"→ {written['manifest'].name}, {written['generated'].name}, "
        f"{written['css'].name}, {written['assets'].name} in {host_dir}"
    )


@app.command("typecheck")
def typecheck(
    host_dir: Annotated[Path, typer.Option("--host-dir")] = Path("client_app"),
    installed_only: Annotated[
        bool,
        typer.Option("--installed-only", help="Allow intentionally uninstalled workspace modules."),
    ] = False,
) -> None:
    """Check the host and installed modules, honouring optional module tsconfigs."""
    from simple_module_hosting.assets import compute_module_assets, framework_assets
    from simple_module_hosting.module_tsconfig import run_typecheck

    if not host_dir.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_dir}", err=True)
        raise typer.Exit(code=1)
    # Typecheck even auth providers omitted from the active host's page manifest.
    assets = [*compute_module_assets(discover_modules(), include_empty=True), *framework_assets()]
    try:
        code = run_typecheck(
            assets, host_dir, repo_root_from_client_app(host_dir), installed_only=installed_only
        )
    except ValueError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    raise typer.Exit(code=code)


@app.command("gen-i18n")
def gen_i18n(
    allow_removals: Annotated[
        bool,
        typer.Option(
            "--allow-removals",
            help="Permit dropping key namespaces of modules not installed here.",
        ),
    ] = False,
    skip_if_missing: Annotated[
        bool, typer.Option("--skip-if-missing", help="Skip if the i18n target package is absent.")
    ] = False,
) -> None:
    """Regenerate the typed i18n key files (keys.generated.ts) without booting the app.

    Writes app-owned aggregates and editable module-local keys. The framework
    repo also retains its central compatibility exports. Installed npm packages
    are never rewritten. Requires an i18n install unless --skip-if-missing is set.
    """
    from simple_module_hosting._project_root import resolve_project_root
    from simple_module_hosting.i18n_manifest import (
        NamespaceRemovalError,
        emit_frontend_types_for_modules,
    )
    from simple_module_hosting.settings import Settings

    project_root = resolve_project_root()
    if skip_if_missing:
        from simple_module_hosting._i18n_target import resolve_i18n_types_dir

        target, _ = resolve_i18n_types_dir(project_root)
        if target is None:
            typer.echo("Skipping gen-i18n: @simple-module-py/i18n not found.")
            return
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("simple_module_hosting.i18n_manifest").setLevel(logging.INFO)
    settings = Settings()
    modules = discover_modules(enabled=settings.modules_enabled, strict=not settings.is_development)
    try:
        emit_frontend_types_for_modules(
            settings,
            modules,
            project_root,
            strict=True,
            allow_removals=allow_removals,
        )
    except (NamespaceRemovalError, FileNotFoundError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo("i18n key files up to date")


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
    sync_module_js_deps(
        host_client_app, collect_module_js_deps(discover_modules()), dry_run=dry_run
    )


def sync_module_js_deps(
    host_client_app: Path, by_module: dict[str, dict[str, str]], *, dry_run: bool = False
) -> None:
    """Install exactly the collected graph used by the generation fingerprint."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not host_client_app.is_dir():
        typer.echo(f"ERROR: client_app directory not found at {host_client_app}", err=True)
        raise typer.Exit(code=1)

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
    client_app = host_client_app.resolve()
    if _declares_workspaces(repo_root) and client_app.is_relative_to(repo_root):
        cwd, target = repo_root, ["--workspace", str(client_app.relative_to(repo_root))]
    else:
        # A flat app's client_app is its own npm project, with no workspace root above it.
        cwd, target = client_app, []

    cmd = [
        npm,
        "install",
        *target,
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
    result = subprocess.run(cmd, cwd=cwd, check=False)
    raise typer.Exit(code=result.returncode)


if __name__ == "__main__":
    app()
