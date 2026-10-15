"""OpenAPI export (#456): served path, schema scope, operation ids, settings."""

from __future__ import annotations

import httpx
import pytest
from fastapi import APIRouter
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.settings import Settings

_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}


def _operations(schema: dict):
    for path, item in schema["paths"].items():
        for method, op in item.items():
            if method in _METHODS:
                yield path, method, op


@pytest.mark.parametrize("field", ["api_title", "api_version", "api_description", "openapi_public"])
def test_fields_are_restart_gated(field: str) -> None:
    extra = HostSettings.model_fields[field].json_schema_extra
    assert extra is not None and extra.get("requires_restart") is True


def test_defaults() -> None:
    hs = HostSettings()
    assert hs.api_title == "SimpleModule"
    assert hs.api_version
    assert hs.openapi_public is False


def test_title_version_description_come_from_settings(settings: Settings) -> None:
    s = settings.model_copy(
        update={"api_title": "Acme", "api_version": "9.9.9", "api_description": "Hello"}
    )
    info = create_app(s).openapi()["info"]
    assert (info["title"], info["version"], info["description"]) == ("Acme", "9.9.9", "Hello")


def test_schema_only_has_api_paths(app) -> None:
    paths = app.openapi()["paths"]
    assert paths
    assert all(p.startswith("/api/") for p in paths), [
        p for p in paths if not p.startswith("/api/")
    ]


def test_operation_ids_unique_and_module_prefixed(app) -> None:
    ids = [op["operationId"] for _, _, op in _operations(app.openapi())]
    assert len(ids) == len(set(ids))
    # no FastAPI default ids (which embed the path and method)
    assert not any("_api_" in i and i.endswith(("_get", "_post", "_put", "_delete")) for i in ids)


def test_route_ids_are_module_and_function() -> None:
    from simple_module_hosting._openapi import make_unique_id_function

    router = APIRouter(tags=["BlogPosts"], generate_unique_id_function=make_unique_id_function())

    @router.get("/a")
    def listing() -> None: ...

    assert router.routes[0].unique_id == "blog_posts_listing"


def test_duplicate_operation_id_is_disambiguated(caplog) -> None:
    from simple_module_hosting._openapi import dedupe_operation_ids

    schema = {
        "paths": {
            "/api/a": {"get": {"operationId": "x_list"}},
            "/api/b": {"get": {"operationId": "x_list"}},
        }
    }
    dedupe_operation_ids(schema)
    ids = [schema["paths"][p]["get"]["operationId"] for p in schema["paths"]]
    assert ids[0] == "x_list" and ids[1] == "x_list_get_api_b"
    assert "x_list" in caplog.text


async def test_not_served_in_production_by_default(settings: Settings) -> None:
    s = settings.model_copy(update={"environment": "production"})
    app = create_app(s)
    assert app.openapi_url is None


async def test_served_when_public_flag_set(settings: Settings) -> None:
    s = settings.model_copy(update={"environment": "production", "openapi_public": True})
    assert create_app(s).openapi_url == "/api/openapi.json"


async def _get(app, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, follow_redirects=False)


async def test_public_flag_serves_schema_anonymously(settings: Settings) -> None:
    s = settings.model_copy(update={"environment": "production", "openapi_public": True})
    r = await _get(create_app(s), "/api/openapi.json")
    assert r.status_code == 200
    assert r.json()["openapi"].startswith("3.")


async def test_unserved_schema_is_not_reachable(settings: Settings) -> None:
    s = settings.model_copy(update={"environment": "production"})
    app = create_app(s)
    assert (await _get(app, "/api/openapi.json")).status_code != 200
    assert (await _get(app, "/openapi.json")).status_code != 200
