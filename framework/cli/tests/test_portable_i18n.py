"""Module keys must work before a consuming app is installed (#958)."""

from simple_module_cli.scaffolding import create_host, create_module


def test_standalone_pages_use_shipped_local_keys(tmp_path):
    dest = tmp_path / "orders"
    create_module(dest, "orders")
    generated = dest / "orders/pages/i18n.generated.ts"
    assert generated.is_file()
    assert "orders.create.title" in generated.read_text()
    assert "interface TranslationResources" in generated.read_text()
    for page in (dest / "orders/pages").glob("*.tsx"):
        source = page.read_text()
        assert "from './i18n.generated'" in source
        assert "t(keys.orders." in source


def test_app_config_uses_versioned_plugin(tmp_path):
    create_host(tmp_path / "host", "demo", [], framework_version="0.0.47")
    client = tmp_path / "host/client_app"
    source = (client / "vite.config.ts").read_text()
    assert "from '@simple-module-py/vite-plugin'" in source
    assert "simpleModule(" in source
    assert "function moduleBareImportResolver" not in source
    assert '"@simple-module-py/vite-plugin": "0.0.47"' in (client / "package.json").read_text()


def test_standalone_local_keys_typecheck_without_app_aggregate(tmp_path, require_cli_asset):
    import json
    import shutil
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    tsc = root / "node_modules/typescript/bin/tsc"
    require_cli_asset(shutil.which("node") is not None and tsc.is_file(), "node/tsc absent")
    dest = tmp_path / "orders"
    create_module(dest, "orders")
    (dest / "node_modules").symlink_to(root / "node_modules", target_is_directory=True)
    (dest / "check.ts").write_text(
        "import { t, keys as compatibilityKeys } from '@simple-module-py/i18n';\n"
        "import { keys } from './orders/pages/i18n.generated';\n"
        "t(keys.orders.create.title);\n"
        "t(compatibilityKeys.orders.create.title);\n"
        "// @ts-expect-error: a typo is not a valid translation key\n"
        "t('orders.create.typo');\n"
    )
    (dest / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": True,
                    "noEmit": True,
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "skipLibCheck": False,
                    "target": "ES2022",
                    "jsx": "react-jsx",
                },
                "files": ["check.ts"],
            }
        )
    )
    result = subprocess.run(
        ["node", str(tsc), "-p", str(dest / "tsconfig.json")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
