"""Effective frontend configs work for editable and wheel-installed modules."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_hosting.frontend.assets import ModuleAssets


def _asset(package: Path) -> ModuleAssets:
    return ModuleAssets(
        name="Orders",
        package_name="orders",
        package_dir=package,
        pages_dir=package / "pages",
        theme_css=None,
        styles_css=None,
    )


def test_gen_pages_writes_defaults_without_changing_modules(tmp_path, monkeypatch):
    from simple_module_hosting.frontend import manifest

    package = tmp_path / "modules" / "orders" / "orders"
    (package / "pages").mkdir(parents=True)
    (package / "pages" / "Browse.tsx").write_text("export default () => null")
    (package.parent / "pyproject.toml").touch()
    output = tmp_path / "host" / "client_app"
    output.mkdir(parents=True)
    (output / "tsconfig.json").write_text("{}")
    monkeypatch.setattr(manifest, "compute_module_assets", lambda modules: [_asset(package)])
    monkeypatch.setattr(
        manifest, "compute_module_pages", lambda modules: {"Orders": package / "pages"}
    )
    monkeypatch.setattr(manifest, "framework_assets", list)

    manifest.write_module_pages_manifest([], output, repo_root=tmp_path)

    config = output / ".module-tsconfig" / "orders.json"
    assert config.is_file()
    data = json.loads(config.read_text())
    assert data["extends"] == str(output / "tsconfig.json")
    assert any(value.endswith("/src/orders/**/*.tsx") for value in data["include"])
    assert data["compilerOptions"]["preserveSymlinks"] is True
    assert not any("tests-js" in value for value in data["include"])
    assert not (package.parent / "tsconfig.json").exists()
    stamp = config.stat().st_mtime_ns
    manifest.write_module_pages_manifest([], output, repo_root=tmp_path)
    assert config.stat().st_mtime_ns == stamp


def test_authored_config_takes_precedence_and_stale_generated_configs_are_unused(tmp_path):
    from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs

    package = tmp_path / "modules" / "orders" / "orders"
    package.mkdir(parents=True)
    (package / "widget.ts").write_text("export const value = 1")
    (package.parent / "pyproject.toml").touch()
    override = package.parent / "tsconfig.json"
    override.write_text('{"extends": "./custom.json"}')
    output = tmp_path / "client_app"
    output.mkdir()

    configs = write_module_tsconfigs([_asset(package)], output)
    assert configs == [override]
    assert override.read_text() == '{"extends": "./custom.json"}'
    assert write_module_tsconfigs([], output) == []


def test_wheel_defaults_resolve_dependencies_from_host(tmp_path):
    from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs

    package = tmp_path / "site-packages" / "orders"
    package.mkdir(parents=True)
    (package / "widget.ts").write_text("export const value = 1")
    output = tmp_path / "app" / "client_app"
    output.mkdir(parents=True)
    configs = write_module_tsconfigs([_asset(package)], output)
    data = json.loads(configs[0].read_text())
    assert "paths" not in data["compilerOptions"]
    assert (output / ".module-tsconfig/src/orders").resolve() == package
    assert not any("tests-js" in value for value in data["include"])


def test_real_typecheck_covers_external_sources_and_host_dependencies(tmp_path):
    import subprocess

    from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs

    repo = Path(__file__).resolve().parents[4]
    output = tmp_path / "host" / "client_app"
    output.mkdir(parents=True)
    (output / "node_modules").symlink_to(repo / "node_modules", target_is_directory=True)
    (output / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2022",
                    "lib": ["ES2022", "DOM"],
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "jsx": "react-jsx",
                    "strict": True,
                    "skipLibCheck": True,
                    "noEmit": True,
                },
            }
        )
    )
    package = tmp_path / "external" / "site-packages" / "orders"
    (package / "pages").mkdir(parents=True)
    page = package / "pages" / "Browse.tsx"
    page.write_text(
        "import { Button } from '@simple-module-py/ui/components/ui/button';\n"
        "import { Link } from '@inertiajs/react';\n"
        "import '@simple-module-py/i18n/inertia';\n"
        "export default () => <Button asChild><Link href='/'>Hi</Link></Button>;"
    )
    from dataclasses import replace

    (package / "token.ts").write_text("export class Token { private value = 1; }")
    (package / "use.ts").write_text(
        "import { Token } from '@custom/orders/token'; export function use(token: Token) {}"
    )
    (package / "caller.ts").write_text(
        "import { Token } from './token'; import { use } from './use'; use(new Token());"
    )
    asset = replace(_asset(package), npm_name="@custom/orders")
    (config,) = write_module_tsconfigs([asset], output)
    cmd = [str(repo / "node_modules/.bin/tsc"), "--noEmit", "-p", str(config)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    (package / "unimported.ts").write_text("const value: string = 42; export { value };")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "unimported.ts" in result.stdout


def test_typecheck_runs_authored_override_and_propagates_compiler_failure(tmp_path):
    from simple_module_hosting.frontend.module_tsconfig import run_typecheck

    repo = Path(__file__).resolve().parents[4]
    output = tmp_path / "client_app"
    output.mkdir()
    (output / "node_modules").symlink_to(repo / "node_modules", target_is_directory=True)
    (output / "main.ts").write_text("export {}")
    (output / "tsconfig.json").write_text(
        '{"files": ["main.ts"], "compilerOptions": {"skipLibCheck": true}}'
    )
    package = tmp_path / "orders" / "orders"
    package.mkdir(parents=True)
    (package.parent / "pyproject.toml").touch()
    (package / "skipped.ts").write_text("const value: string = 42;")
    source = package / "checked.ts"
    source.write_text("export {}")
    (package.parent / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"noEmit": True, "skipLibCheck": True},
                "files": [str(source)],
            }
        )
    )
    assert run_typecheck([_asset(package)], output, tmp_path) == 0
    source.write_text("const value: string = 42;")
    assert run_typecheck([_asset(package)], output, tmp_path) != 0


def test_typecheck_discovery_includes_packages_without_vite_assets(tmp_path, monkeypatch):
    from simple_module_core import ModuleBase, ModuleMeta
    from simple_module_hosting.frontend.assets import compute_module_assets

    class Orders(ModuleBase):
        meta = ModuleMeta(name="Orders")

    package = tmp_path / "orders"
    (package / "contracts").mkdir(parents=True)
    (package / "contracts/view.ts").write_text("export interface View { id: string }")
    monkeypatch.setattr(
        "simple_module_hosting.frontend.assets.importlib.resources.files", lambda _: package
    )
    assert compute_module_assets([Orders()]) == []
    assert compute_module_assets([Orders()], include_empty=True)[0].package_dir == package


def test_repository_gate_rejects_undiscovered_frontend_module(tmp_path):
    import pytest
    from simple_module_hosting.frontend.module_tsconfig import check_local_coverage

    package = tmp_path / "modules/orders/orders"
    package.mkdir(parents=True)
    (package.parent / "pyproject.toml").write_text('[project]\nname = "orders"')
    (package / "widget.tsx").write_text("export default () => null")
    with pytest.raises(ValueError, match="not discovered"):
        check_local_coverage([], tmp_path)
    check_local_coverage([_asset(package)], tmp_path)


def test_generated_alias_cleanup_preserves_module_sources(tmp_path):
    from dataclasses import replace

    from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs

    package = tmp_path / "orders"
    package.mkdir()
    source = package / "widget.ts"
    source.write_text("export {}")
    output = tmp_path / "client_app"
    output.mkdir()
    asset = replace(_asset(package), npm_name="@custom/orders")
    write_module_tsconfigs([asset], output)
    alias = output / ".module-tsconfig/node_modules/@custom/orders"
    assert alias.resolve() == package
    assert write_module_tsconfigs([], output) == []
    assert not alias.exists()
    assert source.is_file()


def test_packaged_override_is_also_honoured_in_editable_install(tmp_path):
    from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs

    package = tmp_path / "orders" / "orders"
    package.mkdir(parents=True)
    (package.parent / "pyproject.toml").touch()
    override = package / "tsconfig.json"
    override.write_text('{"files": ["widget.ts"]}')
    output = tmp_path / "client_app"
    output.mkdir()
    assert write_module_tsconfigs([_asset(package)], output) == [override]


def test_repository_coverage_uses_entrypoint_package_not_directory_name(tmp_path):
    from simple_module_hosting.frontend.module_tsconfig import check_local_coverage

    package = tmp_path / "modules" / "custom-slug" / "orders"
    package.mkdir(parents=True)
    (package.parent / "pyproject.toml").write_text(
        '[project.entry-points.simple_module]\norders = "orders.module:OrdersModule"'
    )
    (package.parent / "tsconfig.json").write_text("{}")
    check_local_coverage([_asset(package)], tmp_path)
