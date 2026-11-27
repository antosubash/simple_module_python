"""Settings' own JSON handlers must also tolerate lone surrogates (#1258)."""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from settings.core._managed_keys import ManagedKeyError, ModuleKeyError
from settings.core.errors import install_exception_handlers
from settings.web.endpoints.module_api import _settings_errors
from simple_module_hosting.error_handling._error_handlers import http_exception_handler


@pytest.mark.parametrize(
    "error,field",
    [
        (ManagedKeyError("key", "/clear/\ud800"), "clear_via"),
        (ModuleKeyError("\ud800", "/edit/\ud800"), "edit_via"),
    ],
)
async def test_settings_domain_errors_replace_surrogates(error, field):
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/error")
    async def fail():
        raise error

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/error")
    assert response.status_code == 422
    response.content.decode("utf-8")
    assert "�" in response.json()["detail"]
    assert response.json()[field].endswith("/�")


async def test_settings_validation_sanitizes_context_without_echoing_input():
    app = FastAPI()
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Module settings validate dynamically inside this context manager.
    @app.get("/validate")
    async def validate():
        with _settings_errors(None):
            raise ValidationError.from_exception_data(
                "Settings",
                [
                    {
                        "type": "value_error",
                        "loc": ("value",),
                        "input": "secret",
                        "ctx": {"error": ValueError("invalid"), "hint": "\ud800"},
                    }
                ],
            )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/validate", headers={"Accept": "application/json"})
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert "input" not in detail
    assert detail["msg"] == "Value error, invalid"
    assert detail["ctx"] == {"error": "invalid", "hint": "�"}
