"""Generated local and app catalogs must compose in one TypeScript program."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from simple_module_core.localization.i18n import I18nRegistry
from simple_module_hosting._i18n_modules import write_module_keys
from simple_module_hosting.i18n_manifest import write_generated_resources


@pytest.mark.parametrize("skip_lib_check", [False, True])
@pytest.mark.parametrize("shared_namespace", [False, True], ids=["same-keys", "shared-namespace"])
def test_app_and_module_catalogs_typecheck(tmp_path, skip_lib_check, shared_namespace):
    root = Path(__file__).resolve().parents[3]
    tsc = root / "node_modules/typescript/bin/tsc"
    if not shutil.which("node") or not tsc.is_file():
        if os.environ.get("CI"):
            pytest.fail("node/tsc required in CI")
        pytest.skip("node/tsc absent")

    locales = tmp_path / "locales"
    locales.mkdir()
    (locales / "en.json").write_text(json.dumps({"nested": {"title": "Title"}}))
    write_module_keys({"shared_catalog": locales}, tmp_path / "module.ts")
    messages = {"shared_catalog.nested.title": "Title"}
    if shared_namespace:
        (locales / "en.json").write_text(json.dumps({"nested": {"action": "Action"}}))
        write_module_keys({"shared_catalog": locales}, tmp_path / "other-module.ts")
        messages["shared_catalog.nested.action"] = "Action"

    registry = I18nRegistry(default_locale="en", supported_locales=["en"])
    registry._messages = {"en": messages}
    write_generated_resources(registry, tmp_path / "app", augment=True)
    (tmp_path / "check.ts").write_text(
        "import { t, keys as compatibilityKeys } from '@simple-module-py/i18n';\n"
        "import { keys as moduleKeys } from './module';\n"
        "import { keys as appKeys } from './app/keys.generated';\n"
        "t(moduleKeys.shared_catalog.nested.title);\n"
        "t(appKeys.shared_catalog.nested.title);\n"
        "t(compatibilityKeys.shared_catalog.nested.title);\n"
        "// @ts-expect-error: unknown keys must still be rejected\n"
        "t('shared_catalog.nested.typo');\n"
        + (
            "import { keys as otherKeys } from './other-module';\n"
            "t(otherKeys.shared_catalog.nested.action);\n"
            "t(compatibilityKeys.shared_catalog.nested.action);\n"
            if shared_namespace
            else ""
        )
    )
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": True,
                    "noEmit": True,
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "skipLibCheck": skip_lib_check,
                    "target": "ES2022",
                    "jsx": "react-jsx",
                    "paths": {"@simple-module-py/i18n": [str(root / "packages/i18n/src/index.ts")]},
                },
                "files": ["check.ts"],
            }
        )
    )
    result = subprocess.run(
        ["node", str(tsc), "-p", str(tmp_path / "tsconfig.json")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
