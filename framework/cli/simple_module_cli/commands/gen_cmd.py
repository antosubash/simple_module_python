"""One incremental frontend preparation step for install, dev, build and verify."""

from __future__ import annotations

import hashlib
import importlib.resources
from pathlib import Path

import typer

from simple_module_cli.migrations._migration_support import resolve_project_root
from simple_module_cli.tooling import _generation_cache
from simple_module_cli.tooling._generation_cache import GenerationCache, file_hashes, source_files


def client_app_dir(root: Path) -> Path:
    for path in (root / "host/client_app", root / "client_app"):
        if path.is_dir():
            return path
    raise ValueError(f"No host/client_app or client_app in {root}")


def _settings_and_modules():
    from simple_module_core import discover_modules
    from simple_module_hosting import merge_host_settings

    settings = merge_host_settings(strict=False)
    return settings, discover_modules(strict=True)


def _sync_deps(client: Path, deps: dict[str, dict[str, str]]) -> None:
    from simple_module_hosting.host_cli import sync_module_js_deps

    try:
        sync_module_js_deps(client, deps)
    except typer.Exit as exc:
        if exc.exit_code:
            raise


def run_generation(project_root: Path | None = None) -> list[str]:
    from simple_module_core import discover_modules, get_module_package_name, select_auth_provider
    from simple_module_core.dotenv import load_dotenv_into_environ
    from simple_module_hosting._i18n_modules import module_key_outputs
    from simple_module_hosting._i18n_target import app_i18n_dir, resolve_i18n_types_dir
    from simple_module_hosting.admin_surfaces import render_admin_surfaces
    from simple_module_hosting.assets import (
        compute_module_assets,
        framework_assets,
        render_assets_json,
    )
    from simple_module_hosting.host_cli import _declares_workspaces
    from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
    from simple_module_hosting.manifest import collect_module_js_deps, write_module_pages_manifest

    from simple_module_cli.commands import openapi_cmd
    from simple_module_cli.commands.openapi_cmd import _build_app
    from simple_module_cli.tooling import openapi_types
    from simple_module_cli.tooling.openapi_types import generate, module_targets

    root = (project_root or resolve_project_root()).resolve()
    client = client_app_dir(root)
    load_dotenv_into_environ(root / ".env")
    settings, installed = _settings_and_modules()
    enabled = settings.modules_enabled
    active = installed if enabled is None else discover_modules(enabled=enabled, strict=True)
    modules = select_auth_provider(active, settings.auth_provider)
    roots = [Path(str(importlib.resources.files(get_module_package_name(m)))) for m in installed]
    hosting = Path(str(importlib.resources.files("simple_module_hosting")))
    cache = GenerationCache(root / ".smpy/gen.json")
    changed = []
    # Code changes in the pipeline itself invalidate old cache formats and decisions.
    version = file_hashes([Path(p) for p in (__file__, _generation_cache.__file__) if p])

    def run(name, inputs, outputs, action):
        if cache.run(name, lambda: {"version": version, "data": inputs()}, outputs, action):
            changed.append(name)

    target, _ = resolve_i18n_types_dir(root)
    if target is None:
        raise FileNotFoundError("@simple-module-py/i18n not found; run npm install first")
    locale_sources = [
        [namespace, str(directory)]
        for m in installed
        for namespace, directory in m.locale_dirs().items()
    ]
    catalogs = [Path(directory) for _namespace, directory in locale_sources]
    catalogs += [hosting / "locales", hosting / "ui_locales", root / "host/locales"]
    i18n_inputs = [p for d in catalogs for p in d.rglob("*.json")]
    run(
        "i18n",
        lambda: {
            "catalogs": file_hashes(i18n_inputs),
            "sources": locale_sources,
            "locales": [settings.i18n_default_locale, settings.i18n_supported_locales],
            "generator": file_hashes(
                [
                    hosting / "i18n_manifest.py",
                    hosting / "_i18n_build.py",
                    hosting / "_i18n_target.py",
                    hosting / "_i18n_modules.py",
                ]
            ),
        },
        [
            directory / name
            for directory in {target, app_i18n_dir(root)} - {None}
            for name in ("keys.generated.ts", "generated-resources.ts")
        ]
        + [path for _, path in module_key_outputs(installed)],
        lambda: emit_frontend_types_for_modules(settings, installed, root, strict=True),
    )

    assets = [*compute_module_assets(modules), *framework_assets()]
    page_sources = [
        p
        for a in assets
        for p in source_files(a.package_dir, {".ts", ".tsx"})
        if p.name != "i18n.generated.ts"
    ]
    run(
        "pages",
        lambda: {
            "assets": render_assets_json(assets),
            "admin_surfaces": render_admin_surfaces(modules),
            "sources": sorted(str(p) for p in page_sources),
            "generator": file_hashes(
                [
                    hosting / "manifest.py",
                    hosting / "assets.py",
                    hosting / "_asset_sources.py",
                    hosting / "page_globs.py",
                    hosting / "admin_surfaces.py",
                    hosting / "frontend_extensions.py",
                ]
            ),
        },
        [
            client / f"modules.{n}"
            for n in ("manifest.json", "generated.ts", "generated.css", "assets.json")
        ],
        lambda: write_module_pages_manifest(modules, client),
    )

    deps = collect_module_js_deps(installed)
    npm_root = root if _declares_workspaces(root) else client
    dep_files = [
        base / "node_modules" / dep / "package.json"
        for block in deps.values()
        for dep in block
        for base in {npm_root, client}
    ]
    manifests = [root / "package.json", client / "package.json", npm_root / "package-lock.json"]
    run(
        "deps",
        lambda: {
            "dependencies": deps,
            "manifests": file_hashes(manifests),
            "generator": file_hashes([hosting / "host_cli.py", hosting / "manifest.py"]),
        },
        dep_files,
        lambda: _sync_deps(client, deps),
    )

    targets = module_targets(modules, root, [])
    api_roots = [*roots, root / "host"]
    if client == root / "client_app":
        api_roots.append(root)
    for package in (
        "simple_module_core",
        "simple_module_db",
        "simple_module_hosting",
        "simple_module_inertia",
    ):
        api_roots.append(Path(str(importlib.resources.files(package))))
    api_files = [p for d in api_roots for p in source_files(d, {".py"})]
    api_files += [
        root / "pyproject.toml",
        root / "uv.lock",
    ]
    api_files += [Path(p) for p in (openapi_cmd.__file__, openapi_types.__file__) if p]

    def api():
        if targets:
            for _target, _changed, untyped in generate(_build_app(root).openapi(), targets, root):
                for operation in untyped:
                    typer.echo(f"untyped response: {operation} (add response_model=)", err=True)

    run(
        "api",
        lambda: {
            "sources": file_hashes(api_files),
            "modules": [[m.meta.name, m.meta.version] for m in modules],
            "auth": settings.auth_provider,
            "settings": hashlib.sha256(
                settings.model_dump_json(exclude={"secret_key", "vite_dev_url"}).encode()
            ).hexdigest(),
        },
        [t.output for t in targets],
        api,
    )
    return changed


def gen_command() -> None:
    """Generate pages, i18n keys, module JS dependencies and API types as needed."""
    try:
        changed = run_generation()
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo("Generated: " + ", ".join(changed) if changed else "Generated files are up to date")
