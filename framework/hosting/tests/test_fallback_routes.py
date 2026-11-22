"""Late slug routes must lose to every ordinary route and mount (#1022)."""

import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, Depends, Request
from fastapi.routing import iter_route_contexts
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.web.spa_mount import SpaMount
from simple_module_db.scoping.tenancy import current_tenant_id
from simple_module_hosting import app_builder
from simple_module_hosting.csrf import RequiresCsrf, get_csrf_token
from simple_module_test import build_test_app
from simple_module_test._schema import _create_all_tables
from simple_module_test.fixtures import _seed_setup_admin
from simple_module_test.inertia import inertia_headers
from simple_module_test.session_cookie import forge_session_cookie
from starlette.staticfiles import StaticFiles


class SlugModule(ModuleBase):
    meta = ModuleMeta(name="Slugs", admin_view_prefix="/admin/slugs")

    def register_routes(self, api_router, view_router):
        @api_router.get("/api/slug-probe")
        async def probe():
            return {"handler": "api"}

    def register_admin_routes(self, admin_router):
        @admin_router.get("/probe")
        async def admin_probe():
            return {"handler": "admin"}

    def register_public_routes(self, registry):
        registry.add_exact("/some-slug", methods={"GET", "POST"})
        registry.add_exact("/some-slug/page", methods={"GET"})

    def register_fallback_routes(self, router):
        nested = APIRouter(dependencies=[Depends(RequiresCsrf())])

        @nested.api_route("/{slug}", methods=["GET", "POST"])
        @nested.get("/{slug}/{page}")
        async def slug_page(request: Request, slug: str, page: str | None = None):
            return {
                "module": self.meta.name,
                "slug": slug,
                "page": page,
                "tenant": current_tenant_id.get(),
                "csrf": get_csrf_token(request),
            }

        router.include_router(nested)


class LaterSlugModule(SlugModule):
    meta = ModuleMeta(name="LaterSlugs", depends_on=["Slugs"])


class PrefixedSlugModule(SlugModule):
    meta = ModuleMeta(name="PrefixedSlugs", view_prefix="/pages")


@pytest.fixture
def fallback_modules(monkeypatch, tmp_path):
    from auth.module import AuthModule
    from users.module import UsersModule

    static = tmp_path / "static"
    static.mkdir()
    (static / "probe.txt").write_text("static asset")
    templates = Path(__file__).resolve().parents[3] / "host" / "templates"
    shutil.copytree(templates, tmp_path / "host" / "templates")
    spa = tmp_path / "spa"
    spa.mkdir()
    (spa / "index.html").write_text("<html>legacy spa</html>")
    first = SlugModule()
    monkeypatch.setattr(first, "static_mounts", lambda: {"/assets": static})
    monkeypatch.setattr(first, "spa_mounts", lambda: [SpaMount("/legacy", spa)])
    modules = [LaterSlugModule(), PrefixedSlugModule(), first, UsersModule(), AuthModule()]
    monkeypatch.setattr(app_builder, "discover_modules", lambda **kwargs: modules)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    return modules


@pytest.fixture(params=["create_app", "build_host_app"])
async def fallback_app(request, settings, monkeypatch, tmp_path, fallback_modules):
    settings = settings.model_copy(update={"multi_tenant": False, "default_tenant": "slug-tenant"})
    host = APIRouter()

    @host.get("/host-page")
    async def host_page():
        return {"handler": "host"}

    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    if request.param == "build_host_app":
        from simple_module_hosting.host import build_host_app

        monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: settings)
        monkeypatch.setattr("simple_module_hosting.logging.setup_logging", lambda **kwargs: None)
        app = build_host_app(tmp_path / "main.py", routers=(host,))
    else:
        app = app_builder.create_app(settings, routers=(host,))
    late = APIRouter()

    @late.get("/late")
    async def late_page():
        return {"handler": "late"}

    app.include_router(late)
    app.mount("/mounted", StaticFiles(directory=tmp_path / "static"))
    # The disposable host has no migrations; lifespan must use the real config.
    root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(root)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(root))
    await _create_all_tables(app.state.sm.db.engine)
    await _seed_setup_admin(app)
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def fallback_client(fallback_app):
    from sqlalchemy import select
    from users.models import User

    async with fallback_app.state.sm.db.session_factory() as session:
        user = (await session.execute(select(User))).scalars().first()
        cookie = forge_session_cookie(
            fallback_app.state.sm.settings.secret_key,
            {"user_id": str(user.id)},
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fallback_app),
        base_url="http://testserver",
        cookies={"session": cookie},
        headers={**inertia_headers(fallback_app), "X-Inertia": "true"},
    ) as client:
        yield client


async def test_users_login_wins_over_fallbacks(fallback_client):
    client = fallback_client
    client.cookies.clear()
    login = await client.get("/users/login")
    assert login.status_code == 200
    assert login.json()["component"] == "Users/Login"


async def test_post_builder_entries_precede_fallbacks_at_startup(fallback_app):
    # Inspect before dispatch, so the first-request guard cannot mask a startup bug.
    paths = [ctx.path for ctx in iter_route_contexts(fallback_app.routes)]
    assert paths.index("/late") < paths.index("/{slug}")
    assert paths.index("/mounted") < paths.index("/{slug}")


async def test_post_builder_handlers_win_after_startup(fallback_client):
    assert (await fallback_client.get("/late")).json() == {"handler": "late"}
    assert (await fallback_client.get("/mounted/probe.txt")).text == "static asset"


async def test_framework_module_host_and_asset_handlers_win(fallback_client):
    client = fallback_client
    admin = await client.get("/admin")
    assert admin.status_code == 200
    assert admin.json()["component"] == "Admin/Overview"
    assert (await client.get("/api/slug-probe")).json() == {"handler": "api"}
    assert (await client.get("/admin/slugs/probe")).json() == {"handler": "admin"}
    assert (await client.get("/host-page")).json() == {"handler": "host"}
    assert (await client.get("/health")).json()["status"] == "healthy"
    assert (await client.get("/setup")).status_code == 404
    assert (await client.get("/assets/probe.txt")).text == "static asset"
    assert (await client.get("/static/probe.txt")).text == "static asset"
    assert (await client.get("/assets/missing.txt")).status_code == 404
    spa = await client.get("/legacy/page", headers={"Accept": "text/html"})
    assert spa.text == "<html>legacy spa</html>"


async def test_slug_fallbacks_follow_dependency_order_and_view_prefix(fallback_client):
    for path, module, slug, page in [
        ("/some-slug", "Slugs", "some-slug", None),
        ("/some-slug/page", "Slugs", "some-slug", "page"),
        ("/pages/article", "PrefixedSlugs", "article", None),
        ("/pages/article/details", "PrefixedSlugs", "article", "details"),
    ]:
        response = await fallback_client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert (data["module"], data["slug"], data["page"]) == (module, slug, page)
        assert data["tenant"] == "slug-tenant"


async def test_public_exemption_auth_and_csrf_apply_to_fallbacks(fallback_client):
    fallback_client.cookies.clear()
    private = await fallback_client.get("/private-slug")
    assert private.status_code == 302
    assert "/users/login" in private.headers["location"]
    public = await fallback_client.get("/some-slug")
    assert public.status_code == 200
    assert (await fallback_client.post("/some-slug")).status_code == 403
    accepted = await fallback_client.post(
        "/some-slug", headers={"X-CSRF-Token": public.json()["csrf"]}
    )
    assert accepted.status_code == 200


def test_effective_routes_end_with_fallbacks(settings, fallback_modules):
    app = app_builder.create_app(settings.model_copy(update={"multi_tenant": False}))
    contexts = list(iter_route_contexts(app.routes))
    paths = [ctx.path for ctx in contexts]
    assert paths[-6:] == [
        "/pages/{slug}/{page}",
        "/pages/{slug}",
        "/{slug}/{page}",
        "/{slug}",
        "/{slug}/{page}",
        "/{slug}",
    ]
    assert paths.index("/users/login") < paths.index("/{slug}")


async def test_single_module_test_helper_mounts_fallbacks():
    app = build_test_app(SlugModule)
    # Session is needed by the sample handler's CSRF token, even for GET.
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/some-slug")
        assert response.status_code == 200
        assert response.json()["module"] == "Slugs"
    assert "/{slug}" not in app.openapi()["paths"]


async def test_fallback_views_refuse_scoped_api_tokens():
    app = build_test_app(SlugModule)

    async def token_request(scope, receive, send):
        scope.setdefault("state", {})["user"] = SimpleNamespace(scopes=["*"])
        await app(scope, receive, send)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=token_request), base_url="http://testserver"
    ) as client:
        assert (await client.get("/some-slug")).status_code == 403
