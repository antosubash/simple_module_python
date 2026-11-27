"""Error payloads containing lone surrogates keep their intended status (#1258)."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from simple_module_core.runtime.exceptions import NotFoundError
from simple_module_hosting.error_handling._error_handlers import (
    http_exception_handler,
    not_found_error_handler,
    request_validation_error_handler,
)
from simple_module_hosting.error_handling.errors import render_error_page
from simple_module_inertia import Inertia, InertiaConfig, inertia_dependency_factory
from simple_module_test import inertia_page
from sqlmodel import Field, SQLModel
from starlette.middleware.sessions import SessionMiddleware


class _Comment(SQLModel):
    comment: str = Field(max_length=100)


class _Comments(SQLModel):
    comments: list[_Comment]


@pytest.fixture
async def surrogate_client(tmp_path):
    (tmp_path / "index.html").write_text(
        "<html><head>{% inertia_head %}</head><body>{% inertia_body %}</body></html>"
    )
    config = InertiaConfig(
        templates=Jinja2Templates(directory=str(tmp_path)),
        dev_url="http://localhost:5050",
        use_flash_errors=True,
        version="",
    )
    inertia_dependency_factory(config)
    app = FastAPI()
    app.state.sm = SimpleNamespace(inertia_config=config)
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(NotFoundError, not_found_error_handler)

    @app.post("/comment")
    async def comment(body: _Comment):
        return {}

    @app.post("/nested")
    async def nested(body: _Comments):
        return {}

    @app.get("/form")
    async def form(request: Request):
        return await Inertia(request, config).render("Form")

    @app.api_route("/errors", methods=["GET", "POST"])
    async def errors():
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "field\ud800", 0),
                    "msg": "bad\udfff",
                    "input": {"key\ud800": ["\ud800", None, 3]},
                    "ctx": {"hint": "\ud800", "valid": "ä😀"},
                }
            ]
        )

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(422, detail={"nested": ["bad\ud800", "ä😀"]})

    @app.get("/not-found")
    async def not_found():
        raise NotFoundError("Comment", "\ud800")

    @app.get("/public-error")
    async def public_error(request: Request):
        return await render_error_page(request, 422, "bad\ud800")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.parametrize("value", ["\ud800", "\udfff", "a\ud800b"])
@pytest.mark.parametrize("nested", [False, True])
async def test_json_validation_replaces_surrogates(surrogate_client, value, nested):
    payload = {"comment": value}
    response = await surrogate_client.post(
        "/nested" if nested else "/comment",
        content=json.dumps({"comments": [payload]} if nested else payload),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    assert response.status_code == 422
    detail = json.loads(response.content.decode("utf-8"))["detail"]
    assert detail[0]["input"] == ("a�b" if value.startswith("a") else "�")
    assert detail[0]["loc"] == (
        ["body", "comments", 0, "comment"] if nested else ["body", "comment"]
    )


async def test_validation_sanitizes_all_error_fields(surrogate_client):
    response = await surrogate_client.get("/errors", headers={"Accept": "application/json"})
    assert response.status_code == 422
    assert json.loads(response.content.decode("utf-8"))["detail"] == [
        {
            "type": "value_error",
            "loc": ["body", "field�", 0],
            "msg": "bad�",
            "input": {"key�": ["�", None, 3]},
            "ctx": {"hint": "�", "valid": "ä😀"},
        }
    ]


@pytest.mark.parametrize("headers", [{"Accept": "text/html"}, {"X-Inertia": "true"}])
async def test_browser_validation_keeps_error_page(surrogate_client, headers):
    response = await surrogate_client.get("/errors", headers=headers)
    assert response.status_code == 422
    response.content.decode("utf-8")
    assert inertia_page(response).component == "Error"


@pytest.mark.parametrize("inertia", [False, True])
async def test_surrogate_body_keeps_browser_validation_behavior(surrogate_client, inertia):
    response = await surrogate_client.post(
        "/comment",
        content='{"comment": "\\ud800"}',
        headers={
            "Content-Type": "application/json",
            "Accept": "text/html",
            **({"X-Inertia": "true", "Referer": "http://testserver/form"} if inertia else {}),
        },
    )
    assert response.status_code == (303 if inertia else 422)
    if inertia:
        response = await surrogate_client.get("/form", headers={"X-Inertia": "true"})
        assert response.status_code == 200
        assert "comment" in response.json()["props"]["errors"]
    else:
        assert inertia_page(response).component == "Error"
    response.content.decode("utf-8")


async def test_inertia_body_errors_survive_redirect_and_json_render(surrogate_client):
    response = await surrogate_client.post(
        "/errors", headers={"X-Inertia": "true", "Referer": "http://testserver/form"}
    )
    assert response.status_code == 303
    page = await surrogate_client.get(response.headers["location"], headers={"X-Inertia": "true"})
    assert page.status_code == 200
    assert json.loads(page.content.decode("utf-8"))["props"]["errors"] == {"field�": "bad�"}


@pytest.mark.parametrize("path,status", [("/http-error", 422), ("/not-found", 404)])
@pytest.mark.parametrize(
    "headers", [{"Accept": "application/json"}, {"Accept": "text/html"}, {"X-Inertia": "true"}]
)
async def test_other_errors_keep_status_and_sanitize(surrogate_client, path, status, headers):
    response = await surrogate_client.get(path, headers=headers)
    assert response.status_code == status
    response.content.decode("utf-8")
    if headers.get("Accept") == "application/json":
        detail = response.json()["detail"]
    else:
        detail = inertia_page(response).props["message"]
    assert "�" in str(detail)


async def test_half_built_error_page_fallback_is_safe():
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    @app.get("/error")
    async def error():
        raise HTTPException(422, "bad\ud800")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/error", headers={"Accept": "text/html"})
    assert response.status_code == 422
    assert response.json() == {"detail": "bad�"}


async def test_public_error_renderer_sanitizes_json(surrogate_client):
    response = await surrogate_client.get("/public-error", headers={"Accept": "application/json"})
    assert response.status_code == 422
    assert response.json() == {"detail": "bad�"}
