"""A fresh app's `make dev` runs without Vite 8 warnings or `npm audit` findings (GH #900)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from simple_module_cli import app_project
from simple_module_cli._app_project_manifests import _APP_NPM_OVERRIDES
from simple_module_cli.app_project import create_app_project

_CLIENT_APP = Path(app_project.__file__).parent / "templates" / "host" / "client_app"
_REPO_ROOT = Path(__file__).resolve().parents[3]


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
    assert "rolldownOptions" in config


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
