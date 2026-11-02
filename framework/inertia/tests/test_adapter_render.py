"""End to end through a real FastAPI app: HTML on a page load, JSON on a visit."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.templating import Jinja2Templates
from httpx import ASGITransport, AsyncClient
from simple_module_inertia import (
    Inertia,
    InertiaConfig,
    InertiaVersionConflictException,
    defer,
    inertia_dependency_factory,
    inertia_version_conflict_exception_handler,
)
from starlette.middleware.sessions import SessionMiddleware

TEMPLATE = (
    "<!doctype html><html><head>{% inertia_head %}</head><body>{% inertia_body %}</body></html>"
)


def _app(tmp_path: Path, version: str = "v1") -> FastAPI:
    (tmp_path / "index.html").write_text(TEMPLATE)
    config = InertiaConfig(
        templates=Jinja2Templates(directory=str(tmp_path)),
        version=version,
        dev_url="http://localhost:5050",
        entrypoint_filename="main.tsx",
        root_directory=".",
        use_flash_errors=True,
    )
    dep = inertia_dependency_factory(config)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.add_exception_handler(
        InertiaVersionConflictException, inertia_version_conflict_exception_handler
    )

    @app.get("/users")
    async def users(inertia: Inertia = Depends(dep)):
        inertia.share(auth={"id": 1})
        return await inertia.render("Users/Index", {"users": [1], "feed": defer(lambda: [2])})

    @app.post("/users")
    async def create(inertia: Inertia = Depends(dep)):
        return inertia.redirect("/users")

    return app


@pytest.fixture
def client(tmp_path):
    return AsyncClient(transport=ASGITransport(app=_app(tmp_path)), base_url="http://testserver")


async def test_full_page_load_renders_the_document_with_the_page_object(client) -> None:
    resp = await client.get("/users")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert 'src="http://localhost:5050/@vite/client"' in resp.text
    assert 'src="http://localhost:5050/main.tsx"' in resp.text
    assert "data-page=" in resp.text
    # htmlsafe_json_dumps leaves double quotes intact, so the page object is
    # readable in the attribute exactly once — no double encoding.
    assert '"url": "/users"' in resp.text
    assert '\\"url\\"' not in resp.text


async def test_an_inertia_visit_gets_the_json_page_object(client) -> None:
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "v1"})
    assert resp.status_code == 200
    assert resp.headers["X-Inertia"] == "true"
    page = resp.json()
    assert page["component"] == "Users/Index"
    assert page["url"] == "/users"
    assert page["version"] == "v1"
    assert page["props"] == {"auth": {"id": 1}, "users": [1], "errors": {}}
    assert page["deferredProps"] == {"default": ["feed"]}
    assert page["sharedProps"] == ["auth"]


async def test_a_stale_get_is_a_409_pointing_at_the_same_url(client) -> None:
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})
    assert resp.status_code == 409
    assert resp.headers["X-Inertia-Location"].endswith("/users")


async def test_a_stale_post_is_not_rejected(client) -> None:
    resp = await client.post("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "old"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/users"


async def test_errors_always_prop_is_present_and_empty_by_default(client) -> None:
    resp = await client.get("/users", headers={"X-Inertia": "true", "X-Inertia-Version": "v1"})
    assert resp.json()["props"]["errors"] == {}
