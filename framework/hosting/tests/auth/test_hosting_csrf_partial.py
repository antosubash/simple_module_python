"""The shared token must refresh even when a partial reload selects only data (#982)."""

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from simple_module_core.access.permissions import PermissionRegistry
from simple_module_core.localization.i18n import I18nRegistry
from simple_module_core.web.menu import MenuRegistry
from simple_module_hosting.auth.csrf import RequiresCsrf, rotate_csrf_token
from simple_module_hosting.frontend.inertia_deps import get_inertia
from simple_module_hosting.pipeline.middleware import InertiaLayoutDataMiddleware
from simple_module_inertia import InertiaConfig, inertia_dependency_factory
from starlette.middleware.sessions import SessionMiddleware


@pytest.fixture
async def page_client(tmp_path):
    (tmp_path / "index.html").write_text("{% inertia_body %}")
    app = FastAPI()
    config = InertiaConfig(templates=Jinja2Templates(directory=tmp_path), version="")
    app.state.inertia_dependency = inertia_dependency_factory(config)
    app.state.sm = SimpleNamespace(
        i18n_registry=I18nRegistry(default_locale="en", supported_locales=["en"])
    )
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=MenuRegistry(),
        permission_registry=PermissionRegistry(),
    )

    class Authenticate:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            request = Request(scope)
            request.state.locale = "en"
            request.state.user = (
                SimpleNamespace(id="u1", roles=[]) if request.session.get("signed_in") else None
            )
            await self.app(scope, receive, send)

    app.add_middleware(Authenticate)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.get("/page")
    async def page(request: Request):
        return await (await get_inertia(request)).render("Page", {"items": [1]})

    @app.post("/login")
    async def login(request: Request):
        request.session.clear()
        request.session["signed_in"] = True
        return {}

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        return {}

    @app.post("/rotate")
    async def rotate(request: Request):
        rotate_csrf_token(request)
        return {}

    @app.post("/mutation", dependencies=[Depends(RequiresCsrf())])
    async def mutation():
        return {}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client


async def test_initial_document_and_login_logout_rotation(page_client):
    from simple_module_test import inertia_page

    await page_client.post("/login")
    first = inertia_page(await page_client.get("/page")).props["csrfToken"]
    assert len(first) >= 32
    assert (await page_client.post("/mutation", headers={"X-CSRF-Token": first})).status_code == 200
    await page_client.post("/logout")
    assert "csrfToken" not in inertia_page(await page_client.get("/page")).props
    await page_client.post("/login")
    second = inertia_page(await page_client.get("/page")).props["csrfToken"]
    assert second != first
    assert (await page_client.post("/mutation", headers={"X-CSRF-Token": first})).status_code == 403
    assert (
        await page_client.post("/mutation", headers={"X-CSRF-Token": second})
    ).status_code == 200


@pytest.mark.parametrize(
    "partial", [{"X-Inertia-Partial-Data": "items"}, {"X-Inertia-Partial-Except": "csrfToken"}]
)
async def test_partial_reload_carries_current_token(page_client, partial):
    await page_client.post("/login")
    first = (await page_client.get("/page", headers={"X-Inertia": "true"})).json()["props"][
        "csrfToken"
    ]
    await page_client.post("/rotate")
    response = await page_client.get(
        "/page", headers={"X-Inertia": "true", "X-Inertia-Partial-Component": "Page", **partial}
    )
    props = response.json()["props"]
    assert props["items"] == [1]
    assert props["csrfToken"] != first
    assert (
        await page_client.post("/mutation", headers={"X-CSRF-Token": props["csrfToken"]})
    ).status_code == 200
