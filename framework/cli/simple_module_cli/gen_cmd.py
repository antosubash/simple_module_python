"""One incremental frontend preparation step for install, dev, build and verify."""

from __future__ import annotations

import hashlib
import importlib.resources
from pathlib import Path

import typer

from simple_module_cli._generation_cache import GenerationCache, file_hashes, source_files
from simple_module_cli._migration_support import resolve_project_root


def client_app_dir(root: Path) -> Path:
    for path in (root / "host/client_app", root / "client_app"):
        if path.is_dir():
            return path
    raise ValueError(f"No host/client_app or client_app in {root}")


def _settings_and_modules():
    from simple_module_core import discover_modules
    from simple_module_hosting import merge_host_settings

    settings = merge_host_settings(strict=False)
    return settings, discover_modules(enabled=settings.modules_enabled, strict=True)


def _sync_deps(client: Path) -> None:
    from simple_module_hosting.host_cli import sync_js_deps

    try:
        sync_js_deps(host_client_app=client, dry_run=False)
    except typer.Exit as exc:
        if exc.exit_code:
            raise


def run_generation(project_root: Path | None = None) -> list[str]:
    from simple_module_core import get_module_package_name, select_auth_provider
    from simple_module_core.dotenv import load_dotenv_into_environ
    from simple_module_hosting._i18n_target import resolve_i18n_types_dir
    from simple_module_hosting.assets import (
        compute_module_assets,
        framework_assets,
        render_assets_json,
    )
    from simple_module_hosting.host_cli import _declares_workspaces
    from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
    from simple_module_hosting.manifest import collect_module_js_deps, write_module_pages_manifest

    from simple_module_cli.openapi_cmd import _build_app
    from simple_module_cli.openapi_types import generate, module_targets

    root = (project_root or resolve_project_root()).resolve()
    client = client_app_dir(root)
    load_dotenv_into_environ(root / ".env")
    settings, installed = _settings_and_modules()
    modules = select_auth_provider(installed, settings.auth_provider)
    roots = [Path(str(importlib.resources.files(get_module_package_name(m)))) for m in installed]
    hosting = Path(str(importlib.resources.files("simple_module_hosting")))
    cache = GenerationCache(root / ".smpy/gen.json")
    changed = []
    # Code changes in the pipeline itself invalidate old cache formats and decisions.
    version = file_hashes([Path(__file__), Path(__file__).with_name("_generation_cache.py")])

    def run(name, inputs, outputs, action):
        if cache.run(name, lambda: {"version": version, "data": inputs()}, outputs, action):
            changed.append(name)

    assets = [*compute_module_assets(modules), *framework_assets()]
    page_sources = [p for a in assets for p in source_files(a.package_dir, {".ts", ".tsx"})]
    run(
        "pages",
        lambda: {
            "assets": render_assets_json(assets),
            "sources": sorted(str(p) for p in page_sources),
            "generator": file_hashes(
                [hosting / "manifest.py", hosting / "assets.py", hosting / "page_globs.py"]
            ),
        },
        [
            client / f"modules.{n}"
            for n in ("manifest.json", "generated.ts", "generated.css", "assets.json")
        ],
        lambda: write_module_pages_manifest(modules, client),
    )

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
                ]
            ),
        },
        [target / "keys.generated.ts", target / "generated-resources.ts"],
        lambda: emit_frontend_types_for_modules(settings, installed, root, strict=True),
    )

    deps = collect_module_js_deps(modules)
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
        lambda: _sync_deps(client),
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
        Path(__file__).with_name("openapi_cmd.py"),
        Path(__file__).with_name("openapi_types.py"),
    ]

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
