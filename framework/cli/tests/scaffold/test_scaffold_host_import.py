"""Generated hosts import from either launch directory, with real router wiring."""

import os
import subprocess
import sys

import pytest
from simple_module_cli.scaffold.app_project import create_app_project


@pytest.mark.parametrize("workspace", [False, True], ids=["flat", "workspace"])
@pytest.mark.parametrize("launch_from_host", [False, True], ids=["elsewhere", "host-dir"])
def test_generated_main_imports(tmp_path, workspace, launch_from_host):
    root = tmp_path / "project"
    host, _ = create_app_project(root, name="demo", selected=[], flat=not workspace)
    (root / ".env").write_text(
        "SM_MODULES_ENABLED=[]\nSM_DATABASE_URL=sqlite+aiosqlite:///:memory:\n"
        f"SM_SECRET_KEY={'k' * 64}\nSM_LOG_LEVEL=ERROR\n"
    )
    with (host / "routes.py").open("a") as routes:
        routes.write("\n@router.get('/api/scaffold-marker')\ndef marker(): return 'ok'\n")
    script = """
import os
import runpy
import sys
from pathlib import Path
namespace = runpy.run_path(sys.argv[1])
app = namespace['app']
assert app.title == 'demo'
assert '/api/scaffold-marker' in app.openapi()['paths']
assert Path.cwd() == Path(sys.argv[2])
assert os.environ['SM_PROJECT_ROOT'] == sys.argv[2]
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(host / "main.py"), str(root)],
        cwd=host if launch_from_host else tmp_path,
        env={k: v for k, v in os.environ.items() if not k.startswith("SM_")},
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("flat", [False, True])
async def test_scaffolded_name_defaults_the_running_app(tmp_path, monkeypatch, flat):
    import runpy

    from simple_module_hosting.config import _preapp_config

    root = tmp_path / "project"
    host, _ = create_app_project(root, name="demo", selected=[], flat=flat)
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setenv("SM_PROJECT_ROOT", str(root))
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SM_MODULES_ENABLED", "[]")
    monkeypatch.setenv("SM_ENVIRONMENT", "testing")
    monkeypatch.setenv("SM_SECRET_KEY", "k" * 64)
    monkeypatch.delenv("SM_API_TITLE", raising=False)
    monkeypatch.setattr(_preapp_config, "load_host_overrides", lambda *args, **kwargs: {})

    app = runpy.run_path(str(host / "main.py"))["app"]
    try:
        assert app.title == "demo"
    finally:
        await app.state.sm.db.engine.dispose()
