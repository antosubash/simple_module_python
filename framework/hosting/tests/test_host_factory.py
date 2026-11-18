"""Host boot order must also hold in a fresh interpreter (#158, #194, #978)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _hosting_settings_db import seed_settings_db


@pytest.fixture(autouse=True)
def _isolate_factory_environment(monkeypatch):
    # Boot writes directly to os.environ, including previously absent dotenv keys.
    monkeypatch.setattr(os, "environ", os.environ.copy())


@pytest.mark.parametrize("layout", ["flat", "workspace"])
def test_factory_loads_environment_before_imports_and_merges_settings(tmp_path, layout):
    root = tmp_path / "project"
    host = root / "host" if layout == "workspace" else root
    host.mkdir(parents=True)
    if layout == "workspace":
        (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["host"]\n')
    templates = (
        Path(__file__).resolve().parents[2] / "cli/simple_module_cli/templates/host/templates"
    )
    shutil.copytree(templates, host / "templates")
    url = seed_settings_db(
        root / "settings.db",
        [("host.tenant_header", "X-Database", "string"), ("host.log_level", "ERROR", "string")],
    )
    (root / ".env").write_text(
        f'SM_DATABASE_URL={url}\nSM_MODULES_ENABLED=["Auth", "Users"]\n'
        f"SM_SECRET_KEY={'k' * 64}\n"
        "HOST_FACTORY_MARKER=loaded\nSM_LOG_FORMAT=text\nSM_DEBUG=false\n"
    )
    (host / "factory_routes.py").write_text(
        "import os\nfrom fastapi import APIRouter\n"
        "assert os.environ['HOST_FACTORY_MARKER'] == 'loaded'\n"
        "router = APIRouter()\n"
        "@router.get('/api/factory-marker')\ndef marker(): return 'ok'\n"
    )
    script = """
import importlib.abc
import logging
import os
import sys
from pathlib import Path
from simple_module_hosting.host import build_host_app

assert 'simple_module_hosting.settings' not in sys.modules
class SettingsGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'simple_module_hosting.settings':
            assert os.environ['HOST_FACTORY_MARKER'] == 'loaded'
sys.meta_path.insert(0, SettingsGuard())
from fastapi import APIRouter
extra = APIRouter()
@extra.get('/api/direct-router')
def direct(): return 'ok'
app = build_host_app(sys.argv[1], routers=('factory_routes:router', extra))
assert Path.cwd() == Path(sys.argv[2])
assert os.environ['SM_PROJECT_ROOT'] == sys.argv[2]
assert str(Path(sys.argv[1]).parent) in sys.path
assert app.state.sm.settings.tenant_header == 'X-Database'
assert app.state.sm.settings.debug is True
assert app.state.sm.settings.log_level == 'ERROR'
assert logging.getLogger().level == logging.ERROR
assert '/api/factory-marker' in app.openapi()['paths']
assert '/api/direct-router' in app.openapi()['paths']
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SM_")}
    env["SM_DEBUG"] = "true"
    result = subprocess.run(
        [sys.executable, "-c", script, str(host / "main.py"), str(root)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "override",
    ["inferred", "argument", "environment", "environment_dot", "relative_environment"],
)
def test_factory_root_and_router_order(tmp_path, monkeypatch, settings, override):
    from fastapi import APIRouter, FastAPI
    from simple_module_hosting.host import build_host_app

    root = tmp_path / "project"
    root.mkdir()
    (root / ".env.example").touch()
    (root / ".env").write_text("HOST_FACTORY_MARKER=loaded\n")
    (root / "main.py").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("HOST_FACTORY_MARKER", raising=False)
    events = []
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: settings)
    monkeypatch.setattr(
        "simple_module_hosting.logging.setup_logging", lambda **kwargs: events.append("logging")
    )
    app = FastAPI()

    def create(received):
        assert received is settings
        events.append("app")
        return app

    monkeypatch.setattr("simple_module_hosting.create_app", create)
    first, second = APIRouter(), APIRouter()

    @first.get("/first")
    def one():
        return 1

    @second.get("/second")
    def two():
        return 2

    kwargs = {}
    expected_root_env = str(root)
    if override == "argument":
        kwargs["project_root"] = root
    elif override in {"environment", "environment_dot", "relative_environment"}:
        if override == "environment_dot":
            expected_root_env += "/."
        monkeypatch.setenv(
            "SM_PROJECT_ROOT",
            "project" if override == "relative_environment" else expected_root_env,
        )
        kwargs["project_root"] = tmp_path / "ignored"
    entry = root / "main.py" if override == "inferred" else tmp_path / "other/host/main.py"
    result = build_host_app(entry, routers=(first, second), **kwargs)
    assert result is app
    assert events == ["logging", "app"]
    assert Path.cwd() == root
    assert os.environ["SM_PROJECT_ROOT"] == expected_root_env
    assert os.environ["HOST_FACTORY_MARKER"] == "loaded"
    assert list(app.openapi()["paths"]) == ["/first", "/second"]


@pytest.mark.parametrize("layout", ["repo", "flat", "flat-named-host", "workspace"])
@pytest.mark.parametrize("cwd_marker", [False, True])
def test_factory_entry_file_root_mounts_static_without_markers(
    tmp_path, monkeypatch, settings, layout, cwd_marker
):
    from fastapi import FastAPI
    from simple_module_hosting._app_boot import mount_host_static
    from simple_module_hosting.host import build_host_app

    root = tmp_path / ("host" if layout == "flat-named-host" else "app")
    host = root if layout.startswith("flat") else root / "host"
    if not layout.startswith("flat"):
        root.mkdir()
        (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["host"]\n')
    static = host / "static"
    (static / "dist").mkdir(parents=True)
    (static / "dist/x.js").write_text("console.log('ok');")
    entry = host / "main.py"
    entry.touch()
    if layout != "repo":
        (host / "alembic.ini").touch()
    cwd = tmp_path / "unrelated" if cwd_marker else root
    cwd.mkdir(exist_ok=True)
    if cwd_marker:
        (cwd / ".git").mkdir()
        (tmp_path / ".env.example").touch()
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: settings)
    monkeypatch.setattr("simple_module_hosting.logging.setup_logging", lambda **kwargs: None)

    def create(_settings):
        app = FastAPI()
        mount_host_static(app, Path(os.environ["SM_PROJECT_ROOT"]))
        return app

    monkeypatch.setattr("simple_module_hosting.create_app", create)
    app = build_host_app(entry)

    assert Path(os.environ["SM_PROJECT_ROOT"]) == root
    assert Path.cwd() == root
    mount = next(route for route in app.routes if route.path == "/static")
    assert Path(mount.app.directory) == static
    assert (Path(mount.app.directory) / "dist/x.js").is_file()


def test_existing_package_exports_are_preserved():
    import simple_module_hosting
    from simple_module_hosting.app_builder import create_app
    from simple_module_hosting.settings import Settings

    assert simple_module_hosting.create_app is create_app
    assert simple_module_hosting.Settings is Settings
    assert all(
        getattr(simple_module_hosting, name) is not None for name in simple_module_hosting.__all__
    )
    with pytest.raises(AttributeError, match="has no attribute"):
        _ = simple_module_hosting.not_an_export


def test_factory_builds_the_same_runtime_as_create_app(tmp_path, monkeypatch, settings):
    from fastapi import APIRouter
    from simple_module_hosting import create_app
    from simple_module_hosting.host import build_host_app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: settings)
    monkeypatch.setattr("simple_module_hosting.logging.setup_logging", lambda **kwargs: None)
    expected = create_app(settings)
    router = APIRouter()

    @router.get("/api/factory-only")
    def marker():
        return "ok"

    actual = build_host_app(tmp_path / "main.py", routers=(router,))
    assert actual.state.sm.settings is settings
    assert [type(m) for m in actual.state.sm.modules] == [
        type(m) for m in expected.state.sm.modules
    ]
    assert [m.cls for m in actual.user_middleware] == [m.cls for m in expected.user_middleware]
    assert actual.openapi()["paths"].keys() - expected.openapi()["paths"].keys() == {
        "/api/factory-only"
    }


@pytest.mark.parametrize(
    ("manifest", "member"),
    [
        ('[tool.uv.workspace]\nmembers = ["host"]\n', True),
        ('[tool.uv.workspace ]\nmembers = ["host"]\n', True),
        ('[tool.uv."workspace"]\nmembers = ["host"]\n', True),
        ("# [tool.uv.workspace]\n[project]\nname = 'x'\n", False),
        ("not = [valid", False),
    ],
)
def test_workspace_membership_parses_the_manifest(tmp_path, manifest, member):
    from simple_module_hosting.host import _is_workspace_member

    (tmp_path / "host").mkdir()
    (tmp_path / "pyproject.toml").write_text(manifest)
    assert _is_workspace_member(tmp_path / "host") is member
