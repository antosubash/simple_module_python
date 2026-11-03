"""Regressions for tab-local catalogs and lazy layout work (#788, #791)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from simple_module_core.i18n import I18nRegistry
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry
from simple_module_hosting._inertia_shared import build_i18n_block
from simple_module_hosting.middleware import InertiaLayoutDataMiddleware
from simple_module_hosting.shared_props import register_inertia_shared_provider
from starlette.requests import Request


def _request(headers=(), session=None):
    registry = I18nRegistry(default_locale="en", supported_locales=["en", "de"])
    registry._messages = {"de": {"hello": "Hallo"}}
    app = FastAPI()
    app.state.sm = SimpleNamespace(i18n_registry=registry)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": list(headers),
            "session": session if session is not None else {},
            "state": {"locale": "de"},
        }
    )


def test_each_tab_reports_its_own_catalog():
    session = {"__i18n_locale": "en", "__i18n_audience": "full"}
    for cached, messages in (
        (b"en:full", {"hello": "Hallo"}),
        (b"de:full", None),
        (b"en:full", {"hello": "Hallo"}),
        (b"de:public", {"hello": "Hallo"}),
    ):
        request = _request([(b"x-inertia", b"1"), (b"x-sm-i18n", cached)], session)
        block = build_i18n_block(request.scope, request)
        assert block["messages"] == messages
        assert block["audience"] == "full"
    assert session == {"__i18n_locale": "en", "__i18n_audience": "full"}


def test_non_page_request_does_not_update_existing_session():
    session = {"__i18n_locale": "en", "__i18n_audience": "full"}
    request = _request(session=session)
    build_i18n_block(request.scope, request)
    assert session["__i18n_locale"] == "en"


def test_non_true_inertia_header_uses_legacy_marker():
    request = _request([(b"x-inertia", b"1")], {"__i18n_locale": "de", "__i18n_audience": "full"})
    assert build_i18n_block(request.scope, request)["messages"] is None


async def test_api_request_does_no_layout_work():
    app = FastAPI()
    provider = AsyncMock(return_value={"branding": "Acme"})
    menu = MenuRegistry()
    menu.get_for_request = AsyncMock(return_value={})
    register_inertia_shared_provider(app, provider)
    app.add_middleware(
        InertiaLayoutDataMiddleware, menu_registry=menu, permission_registry=PermissionRegistry()
    )

    @app.middleware("http")
    async def authenticate(request, call_next):
        request.state.user = SimpleNamespace(id="u1", roles=["admin"])
        request.scope["session"] = {"__i18n_locale": "en"}
        request.state.locale = "de"
        return await call_next(request)

    @app.get("/api/example")
    async def api(request: Request):
        assert request.state.resolved_permissions == {"*"}
        assert request.scope["session"] == {"__i18n_locale": "en"}
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        assert (await client.get("/api/example")).json() == {"ok": True}
    provider.assert_not_called()
    menu.get_for_request.assert_not_called()


async def test_page_and_error_render_resolve_layout_once(tmp_path):
    from fastapi.templating import Jinja2Templates
    from simple_module_hosting._error_page import render_error_page
    from simple_module_hosting._inertia_shared import resolve_inertia_shared
    from simple_module_hosting.inertia_deps import get_inertia
    from simple_module_inertia import InertiaConfig, inertia_dependency_factory
    from starlette.middleware.sessions import SessionMiddleware

    app = FastAPI()
    registry = I18nRegistry(default_locale="en", supported_locales=["en"])
    registry._messages = {"en": {"hello": "Hello"}}
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="")
    app.state.sm = SimpleNamespace(i18n_registry=registry, inertia_config=config)
    app.state.inertia_dependency = inertia_dependency_factory(config)
    app.state.principal_serializer = lambda user: {"id": user.id}
    calls = []

    async def provider(request):
        calls.append(request.url.path)
        return {"branding": "Acme"}

    register_inertia_shared_provider(app, provider)
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )

    class SeedUser:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            request = Request(scope)
            request.state.user = SimpleNamespace(id="u1", roles=["admin"])
            request.state.locale = "en"
            await self.app(scope, receive, send)

    app.add_middleware(SeedUser)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/page")
    async def page(request: Request):
        inertia = await get_inertia(request)
        shared = await resolve_inertia_shared(request)
        assert shared is request.state.inertia_shared
        assert shared is await resolve_inertia_shared(request)
        return await inertia.render("Page")

    @app.get("/error")
    async def error(request: Request):
        return await render_error_page(request, 404, "Missing")

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for path, status in (("/page", 200), ("/error", 404)):
            response = await client.get(path, headers={"X-Inertia": "1", "X-SM-I18n": "en:public"})
            assert response.status_code == status
            props = response.json()["props"]
            assert props["auth"]["user"] == {"id": "u1"}
            assert "menus" in props
            assert props["i18n"]["messages"] == {"hello": "Hello"}
            assert props["csrfToken"]
            assert props["branding"] == "Acme"
    assert calls == ["/page", "/error"]


def test_empty_inertia_header_still_negotiates_an_error_page():
    from simple_module_hosting._error_negotiation import _wants_json

    request = Request(
        {
            "type": "http",
            "path": "/api/example",
            "headers": [(b"x-inertia", b"")],
        }
    )
    assert _wants_json(request) is False


def test_catalog_header_does_not_create_an_anonymous_session():
    request = _request([(b"x-inertia", b"1"), (b"x-sm-i18n", b"en:public")])
    block = build_i18n_block(request.scope, request, is_authenticated=False)
    assert block["audience"] == "public"
    assert block["messages"] == {"hello": "Hallo"}
    assert request.session == {}


def test_document_always_sends_catalog_even_with_matching_header():
    request = _request([(b"x-sm-i18n", b"de:full")])
    assert build_i18n_block(request.scope, request)["messages"] == {"hello": "Hallo"}


async def test_late_resolution_runs_in_the_middleware_context():
    """The 500 page resolves after TenantMiddleware unbound its tenant; providers must
    still see the request's tenant (the context captured by the layout middleware)."""
    import contextvars

    from simple_module_db.tenancy import current_tenant_id
    from simple_module_hosting._inertia_shared import resolve_inertia_shared

    async def factory():
        return {"tenant": current_tenant_id.get()}

    token = current_tenant_id.set("tenant-a")
    captured = contextvars.copy_context()
    current_tenant_id.reset(token)  # what leaving TenantMiddleware does
    request = SimpleNamespace(
        state=SimpleNamespace(inertia_shared_factory=factory, inertia_shared_context=captured)
    )
    assert (await resolve_inertia_shared(request))["tenant"] == "tenant-a"
