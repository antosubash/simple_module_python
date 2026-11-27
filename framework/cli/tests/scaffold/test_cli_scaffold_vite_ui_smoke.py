"""Smoke: this checkout's ``@simple-module-py/ui`` optimises under the scaffold's Vite.

GH #1245: Vite 8.4 (Rolldown 1.3) failed dependency optimisation on a fresh app
because the ui package imported itself by name. This installs the locally packed
ui + i18n packages next to the newest Vite the scaffold allows and runs the dev
optimiser on them. Needs network + npm, so it carries the ``e2e`` marker.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from simple_module_cli.scaffold._app_project_manifests import _APP_NPM_DEPS, _APP_NPM_DEV_DEPS

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SMOKE_SCRIPT = Path(__file__).with_name("vite_ui_optimize_smoke.mjs")
_LOCAL_PACKAGES = ("ui", "i18n")


def _pack(package: str, dest: Path) -> Path:
    out = subprocess.run(
        ["npm", "pack", str(_REPO_ROOT / "packages" / package), "--pack-destination", str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest / out.stdout.strip().splitlines()[-1]


def test_ui_package_optimises_under_the_scaffolds_vite(tmp_path: Path, require_cli_asset) -> None:
    require_cli_asset(shutil.which("npm") is not None, "npm not installed")
    tarballs = {f"@simple-module-py/{name}": _pack(name, tmp_path) for name in _LOCAL_PACKAGES}
    app = tmp_path / "app"
    app.mkdir()
    dependencies = {**_APP_NPM_DEPS, **{name: f"file:{path}" for name, path in tarballs.items()}}
    manifest = {
        "name": "vite-ui-smoke",
        "private": True,
        "type": "module",
        "dependencies": dependencies,
        "devDependencies": {"vite": _APP_NPM_DEV_DEPS["vite"]},
    }
    (app / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(
        ["npm", "install", "--no-audit", "--no-fund", "--loglevel=error"],
        cwd=app,
        check=True,
        timeout=600,
    )

    # Resolve Vite from the temporary app, not from the helper's checkout path.
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", _SMOKE_SCRIPT.read_text(encoding="utf-8")],
        cwd=app,
        capture_output=True,
        text=True,
        timeout=90,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "@simple-module-py/ui" in json.loads(result.stdout)["optimized"]
