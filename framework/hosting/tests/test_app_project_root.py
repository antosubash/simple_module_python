"""App creation resolves the host root after the builder has been imported (#1081)."""

from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from starlette.routing import Mount


async def test_static_mount_uses_current_project_root(monkeypatch, tmp_path):
    static = tmp_path / "host" / "static"
    static.mkdir(parents=True)
    (tmp_path / "host" / "templates").mkdir()
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    app = create_app(
        Settings(environment="testing", modules_enabled=[], database_url="sqlite+aiosqlite://")
    )
    try:
        mounts = [route for route in app.routes if isinstance(route, Mount)]
        assert next(route for route in mounts if route.path == "/static").app.directory == static
    finally:
        await app.state.sm.db.engine.dispose()
