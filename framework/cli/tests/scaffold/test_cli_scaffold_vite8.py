"""A fresh app's `make dev` runs without Vite 8 warnings or `npm audit` findings (GH #900)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import simple_module_cli
from simple_module_cli.scaffold._app_project_manifests import _APP_NPM_OVERRIDES
from simple_module_cli.scaffold.app_project import create_app_project

_CLIENT_APP = Path(simple_module_cli.__file__).parent / "templates" / "host" / "client_app"
_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_vite_config_loads_under_the_native_config_loader() -> None:
    """Vite 8 warns about `__dirname` and extensionless relative imports."""
    config = (_CLIENT_APP / "vite.config.ts").read_text(encoding="utf-8")
    assert "__dirname" not in config
    relative = re.findall(r"from '(\.[^']+)'", config)
    assert relative, "expected the config's helper imports"
    assert all(spec.endswith(".ts") for spec in relative), relative
    tsconfig = (_CLIENT_APP / "tsconfig.json").read_text(encoding="utf-8")
    assert '"allowImportingTsExtensions": true' in tsconfig


def test_vite_config_uses_rolldown_options() -> None:
    """`optimizeDeps.esbuildOptions` is deprecated since Vite moved to Rolldown."""
    config = (_CLIENT_APP / "vite.config.ts").read_text(encoding="utf-8")
    assert "esbuildOptions" not in config
    assert "simpleModule(" in config
    plugin = (_REPO_ROOT / "packages/vite-plugin/src/index.ts").read_text()
    assert "rolldownOptions" in plugin


@pytest.mark.parametrize("flat", [False, True])
def test_root_package_json_overrides_the_audited_dependency(tmp_path: Path, flat: bool) -> None:
    target = tmp_path / "app"
    create_app_project(target, name="app", db="sqlite", tenancy=False, selected=[], flat=flat)
    pkg = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert pkg["overrides"] == _APP_NPM_OVERRIDES


def test_app_overrides_match_this_repos() -> None:
    """The repo's own root package.json is what CI audits; keep the two in step."""
    repo_pkg = json.loads((_REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    for name, spec in _APP_NPM_OVERRIDES.items():
        assert repo_pkg["overrides"][name] == spec


@pytest.mark.parametrize("flat", [False, True])
def test_scaffold_caps_vite_before_the_8_4_optimizer_regression(tmp_path: Path, flat: bool) -> None:
    """GH #1212: both installed manifests must exclude the broken Vite minor."""
    target = tmp_path / "app"
    create_app_project(target, name="app", db="sqlite", tenancy=False, selected=[], flat=flat)
    client = target / ("client_app" if flat else "host/client_app")
    manifests = [client / "package.json"]
    if flat:
        manifests.append(target / "package.json")
    for manifest in manifests:
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
        assert pkg["devDependencies"]["vite"] == "~8.3.7", manifest


def test_repo_and_lockfile_use_the_scaffolds_capped_vite_range() -> None:
    lock = json.loads((_REPO_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    for location in ("", "host/client_app"):
        manifest = _REPO_ROOT / location / "package.json"
        pkg = json.loads(manifest.read_text(encoding="utf-8"))
        assert pkg["devDependencies"]["vite"] == "~8.3.7", manifest
        assert lock["packages"][location]["devDependencies"]["vite"] == "~8.3.7"
    assert lock["packages"]["node_modules/vite"]["version"] == "8.3.7"
