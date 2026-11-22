"""Module keys must work before a consuming app is installed (#958)."""

import subprocess
import sys

import pytest
from simple_module_cli.scaffold.scaffolding import create_host, create_module


def test_scaffolding_without_other_framework_packages(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys
from pathlib import Path

class CliOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('simple_module_') and not fullname.startswith('simple_module_cli'):
            raise ModuleNotFoundError(fullname)

sys.meta_path.insert(0, CliOnly())
from simple_module_cli.scaffold.app_project import create_app_project
from simple_module_cli.scaffold.scaffolding import create_module
create_module(Path(sys.argv[1]), 'orders')
create_app_project(Path(sys.argv[2]), name='demo', selected=[])
""",
            str(tmp_path / "orders"),
            str(tmp_path / "app"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "orders.create.title" in (tmp_path / "orders/orders/pages/i18n.generated.ts").read_text()
    assert (
        "hello.create.title"
        in (tmp_path / "app/modules/hello/hello/pages/i18n.generated.ts").read_text()
    )


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


@pytest.mark.parametrize("app_catalog", [False, True], ids=["standalone", "with-app"])
def test_scaffolded_keys_typecheck(tmp_path, require_cli_asset, app_catalog):
    import json
    import shutil
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    tsc = root / "node_modules/typescript/bin/tsc"
    require_cli_asset(shutil.which("node") is not None and tsc.is_file(), "node/tsc absent")
    dest = tmp_path / "orders"
    create_module(dest, "orders")
    (dest / "node_modules").symlink_to(root / "node_modules", target_is_directory=True)
    if app_catalog:
        from simple_module_core.localization.i18n import I18nRegistry
        from simple_module_hosting.i18n.i18n_manifest import write_generated_resources

        registry = I18nRegistry(default_locale="en", supported_locales=["en"])
        registry.add_source("orders", dest / "orders/locales")
        registry.load()
        write_generated_resources(registry, dest / "app", augment=True)
    (dest / "check.ts").write_text(
        "import { t } from '@simple-module-py/i18n';\n"
        "import { keys } from './orders/pages/i18n.generated';\n"
        "t(keys.orders.create.title);\n"
        "// @ts-expect-error: a typo is not a valid translation key\n"
        "t('orders.create.typo');\n"
        + (
            "import { keys as appKeys } from './app/keys.generated';\n"
            "t(appKeys.orders.create.title);\n"
            if app_catalog
            else ""
        )
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
