"""Stage placement controls the actual request context, including short circuits."""

import httpx
import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_db import current_tenant_id
from simple_module_hosting import add_middleware
from simple_module_hosting.boot import app_builder
from starlette.requests import Request
from starlette.responses import JSONResponse


@pytest.mark.parametrize("position", [{"after": "tenant"}, {"stage": "after_tenant"}])
async def test_module_after_tenant_sees_tenant_and_locale(settings, monkeypatch, position):
    observations = []

    class Probe:
        def __init__(self, app, label):
            self.app = app
            self.label = label

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                request = Request(scope)
                observations.append(
                    (
                        self.label,
                        "session" in scope,
                        getattr(request.state, "tenant_id", "unresolved"),
                        getattr(request.state, "locale", "unresolved"),
                        current_tenant_id.get(),
                    )
                )
                if self.label == "after":
                    await JSONResponse({"ok": True})(scope, receive, send)
                    return
            await self.app(scope, receive, send)

    class Example(ModuleBase):
        meta = ModuleMeta(name="Example")

        def register_public_routes(self, registry):
            registry.add_exact("/stage-probe")

        def register_middleware(self, app):
            add_middleware(app, Probe, stage="before_session", label="before")
            app.add_middleware(Probe, label="default")
            add_middleware(app, Probe, **position, label="after")

    discover = app_builder.discover_modules
    monkeypatch.setattr(app_builder, "discover_modules", lambda **kw: [*discover(**kw), Example()])
    settings = settings.model_copy(
        update={"multi_tenant": True, "i18n_supported_locales": ["en", "de"]}
    )

    def customize(app):
        async def resolver(request):
            return "tenant-955"

        app.state.tenant_resolver = resolver

    app = app_builder.create_app(settings, customize=customize)
    original = current_tenant_id.get()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.get("/stage-probe", headers={"Accept-Language": "de"})
        assert response.status_code == 200
        assert observations == [
            ("before", False, "unresolved", "unresolved", original),
            ("default", True, "unresolved", "unresolved", original),
            ("after", True, "tenant-955", "de", "tenant-955"),
        ]
        assert current_tenant_id.get() == original
        assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        await app.state.sm.db.engine.dispose()
