"""A scaffolded app and module pass the app's own lint gates (GH #896)."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from simple_module_cli._app_project_manifests import _APP_PY_DEV_DEPS
from simple_module_cli._lint_tooling import TY_REQUIREMENT
from simple_module_cli.app_project import create_app_project
from simple_module_cli.scaffolding import create_host, create_module, create_workspace

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ruff() -> str:
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not installed")
    return ruff


def _locked_version(package: str) -> str:
    lock = tomllib.loads((_REPO_ROOT / "uv.lock").read_text())
    return next(p["version"] for p in lock["package"] if p["name"] == package)


def test_ty_requirement_admits_the_locked_ty() -> None:
    """The scaffold's ty range must contain the ty this repo is tested on; a
    lock bump past it means re-checking the scaffold's ty rules first."""
    assert Requirement(TY_REQUIREMENT).specifier.contains(_locked_version("ty"))


def test_both_scaffold_layouts_pin_ty_to_the_tested_range(tmp_path: Path) -> None:
    assert TY_REQUIREMENT in _APP_PY_DEV_DEPS
    create_workspace(tmp_path / "ws", "demo")
    dev = tomllib.loads((tmp_path / "ws" / "pyproject.toml").read_text())["dependency-groups"]
    assert TY_REQUIREMENT in dev["dev"]


def test_standalone_host_installs_the_ruff_its_alembic_hook_runs(tmp_path: Path) -> None:
    """``smpy create-host`` has no workspace root, so the host itself needs ruff."""
    create_host(tmp_path / "host", "demo", modules=[])
    dev = tomllib.loads((tmp_path / "host" / "pyproject.toml").read_text())["dependency-groups"]
    assert any(Requirement(d).name == "ruff" for d in dev["dev"])
    assert "post_write_hooks" in (tmp_path / "host" / "alembic.ini").read_text()


@pytest.mark.parametrize(("framework_repo", "expected"), [(False, False), (True, True)])
def test_model_config_ignore_only_where_ty_checks_assignments(
    tmp_path: Path, framework_repo: bool, expected: bool
) -> None:
    """Apps turn ty's invalid-assignment off, so the ignore would be unused there."""
    dest = create_module(tmp_path / "orders", "orders", framework_repo=framework_repo)
    schemas = (dest / "orders" / "contracts" / "schemas.py").read_text()
    assert ("# ty: ignore[invalid-assignment]" in schemas) is expected


@pytest.mark.parametrize("name", ["bookmarks", "group", "g", "g_x", "a2", "zebra"])
def test_module_imports_are_sorted_for_any_package_name(tmp_path: Path, name: str) -> None:
    """``PERM_GROUP`` sorts before or after ``PERM_<PACKAGE>_*`` depending on the name."""
    app = tmp_path / "app"
    create_app_project(app, name="app", db="sqlite", tenancy=False, selected=[])
    create_module(app / "modules" / name, name, standalone=False)
    result = subprocess.run(
        [_ruff(), "check", "--select", "I", f"modules/{name}"],
        cwd=app,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_new_revision_is_formatted_by_the_write_hook(tmp_path: Path) -> None:
    """``alembic revision`` runs ruff on the file, so a new revision passes lint."""
    ruff = _ruff()
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("the hook runs `python -m ruff`; ruff is not importable here")
    app = tmp_path / "app"
    create_app_project(app, name="app", db="sqlite", tenancy=False, selected=[])
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "host/alembic.ini", "revision", "-m", "add x"],
        cwd=app,
        check=True,
        capture_output=True,
    )
    [revision] = (app / "host" / "migrations" / "versions").glob("*_add_x.py")
    fmt = subprocess.run([ruff, "format", "--check", str(revision)], cwd=app, capture_output=True)
    assert fmt.returncode == 0, fmt.stdout
    # F401 is not selected: an empty revision does not use sa/op yet, and the
    # hook deliberately keeps those imports for its author.
    check = subprocess.run(
        [ruff, "check", "--select", "I,W,E", str(revision)],
        cwd=app,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout
