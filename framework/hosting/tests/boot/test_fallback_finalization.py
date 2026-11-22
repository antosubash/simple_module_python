"""Fallback precedence after host composition and at bare mount prefixes (#1022)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.web.spa_mount import SpaMount
from simple_module_hosting.auth.auth_policy import login_redirect_url
from simple_module_hosting.boot import _fallback_routes, _lifespan, app_builder
from simple_module_hosting.boot._app_boot import mount_host_static
from simple_module_hosting.boot._module_routes import wire_fallback_routes
from simple_module_hosting.boot._phase_helpers import mount_module_static_dirs
from simple_module_test import build_test_app
from starlette.responses import PlainTextResponse


class FallbackOnly(ModuleBase):
    meta = ModuleMeta(name="A")

    def register_fallback_routes(self, router):
        @router.get("/{path:path}")
        async def fallback(path: str):
            return {"handler": "fallback"}


class OrdinaryViews(ModuleBase):
    meta = ModuleMeta(name="B", view_prefix="/reports")

    def register_routes(self, api_router, view_router):
        @view_router.get("/")
        async def reports():
            return {"handler": "reports"}


def _add_host_routes(app):
    router = APIRouter()

    @router.get("/late")
    async def late():
        return {"handler": "late"}

    app.include_router(router)
    mounted = FastAPI()

    @mounted.get("/file.txt")
    async def file():
        return PlainTextResponse("late mounted asset")

    app.mount("/mounted", mounted)


async def test_post_builder_routes_and_mounts_win_without_lifespan():
    app = build_test_app(FallbackOnly)
    _add_host_routes(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/late")).json() == {"handler": "late"}
        assert (await client.get("/mounted/file.txt")).text == "late mounted asset"
        assert (await client.get("/mounted/missing.txt")).status_code == 404
        assert (await client.get("/unknown")).json() == {"handler": "fallback"}


def test_concurrent_first_dispatches_preserve_ordinary_routes(monkeypatch):
    app = build_test_app(FallbackOnly)
    fallback = app.routes[-1]
    _add_host_routes(app)
    # Share one middleware instance, as a running server would.
    app.middleware_stack = app.build_middleware_stack()
    first_paused, second_finished = Event(), Event()
    first_thread = None
    real_getattr = getattr

    def pause_during_scan(obj, name, default=None):
        if (
            obj is fallback
            and name == "_sm_fallback"
            and get_ident() == first_thread
            and not first_paused.is_set()
        ):
            first_paused.set()
            # Let an unprotected second finalizer reorder the list mid-scan.
            # With serialization it must wait instead, so release after the deadline.
            second_finished.wait(timeout=1)
        return real_getattr(obj, name, default)

    monkeypatch.setattr(_fallback_routes, "getattr", pause_during_scan, raising=False)

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get("/late")

    def dispatch(first=False):
        nonlocal first_thread
        if first:
            first_thread = get_ident()
        try:
            return asyncio.run(request())
        finally:
            if not first:
                second_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(dispatch, True)
        assert first_paused.wait(timeout=5)
        second = pool.submit(dispatch)
        responses = [first.result(timeout=5), second.result(timeout=5)]
    responses.append(asyncio.run(request()))
    for response in responses:
        assert response.status_code == 200
        assert response.json() == {"handler": "late"}


async def test_lifespan_finalizes_after_startup_hooks(monkeypatch):
    module = FallbackOnly()

    async def startup(app):
        _add_host_routes(app)

    module.on_startup = startup
    app = build_test_app(module)
    app.state.sm = SimpleNamespace(
        settings=SimpleNamespace(environment="testing"),
        db=SimpleNamespace(engine=SimpleNamespace(dispose=AsyncMock())),
    )
    monkeypatch.setattr(_lifespan, "migration_status", AsyncMock(return_value={"is_current": True}))
    monkeypatch.setattr(_lifespan, "hydrate_settings_from_db", AsyncMock())
    async with _lifespan.build_lifespan([module])(app):
        from fastapi.routing import iter_route_contexts

        paths = [ctx.path for ctx in iter_route_contexts(app.routes)]
        assert paths.index("/late") < paths.index("/{path:path}")
        assert paths.index("/mounted") < paths.index("/{path:path}")


@pytest.fixture
def framework_mount_app(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "probe.txt").write_text("static asset")
    spa = tmp_path / "spa"
    spa.mkdir()
    (spa / "index.html").write_text("legacy spa")
    module = FallbackOnly()
    module.static_mounts = lambda: {"/assets": static}
    module.spa_mounts = lambda: [SpaMount("/legacy", spa)]
    app = FastAPI()
    mount_host_static(app, tmp_path)
    mount_module_static_dirs(app, [module])
    wire_fallback_routes(app, module)
    return app


@pytest.mark.parametrize("root_path", ["", "/deployment"])
@pytest.mark.parametrize("prefix", ["/static", "/assets", "/legacy"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
async def test_bare_framework_mount_redirect_preserves_url(
    framework_mount_app, prefix, root_path, method
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=framework_mount_app, root_path=root_path),
        base_url="http://testserver",
    ) as client:
        response = await client.request(method, f"{root_path}{prefix}?q=a%2Fb&x=1")
        assert response.status_code == 307
        assert response.headers["location"] == (
            f"http://testserver{root_path}{prefix}/?q=a%2Fb&x=1"
        )


@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS"])
async def test_explicit_bare_mount_route_wins(framework_mount_app, method):
    @framework_mount_app.get("/assets")
    async def assets():
        return {"handler": "assets"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=framework_mount_app), base_url="http://testserver"
    ) as client:
        response = await client.request(method, "/assets")
        if method == "GET":
            assert response.status_code == 200
            assert response.json() == {"handler": "assets"}
        else:
            assert response.status_code == 405
            assert response.headers["allow"] == "GET"
            assert "location" not in response.headers


async def test_disabled_slash_redirects_stay_disabled(framework_mount_app):
    framework_mount_app.router.redirect_slashes = False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=framework_mount_app), base_url="http://testserver"
    ) as client:
        response = await client.get("/assets")
        assert response.status_code == 200
        assert response.json() == {"handler": "fallback"}


@pytest.mark.parametrize("prefix", ["/static", "/assets", "/legacy"])
async def test_trailing_mount_urls_keep_mount_ownership(framework_mount_app, prefix):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=framework_mount_app), base_url="http://testserver"
    ) as client:
        trailing = await client.get(f"{prefix}/", headers={"Accept": "text/html"})
        assert trailing.status_code == (200 if prefix == "/legacy" else 404)
        asset = await client.get(f"{prefix}/probe.txt")
        assert asset.status_code == (404 if prefix == "/legacy" else 200)


@pytest.mark.parametrize("discovery_order", ["fallback_first", "ordinary_first"])
def test_login_destination_preserves_discovery_order(
    monkeypatch, settings, isolated_host_root, discovery_order
):
    modules = [FallbackOnly(), OrdinaryViews()]
    if discovery_order == "ordinary_first":
        modules[0].meta = ModuleMeta(name="A", depends_on=["B"])
    monkeypatch.setattr(app_builder, "discover_modules", lambda **kwargs: modules)
    app = app_builder.create_app(settings.model_copy(update={"multi_tenant": False}))
    assert list(app.state.sm.view_prefixes) == (
        ["A", "B"] if discovery_order == "fallback_first" else ["B", "A"]
    )
    assert login_redirect_url(app, "Users") == (
        "/" if discovery_order == "fallback_first" else "/reports/"
    )
