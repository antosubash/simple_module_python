"""Shared clients send the configured version without enabling Inertia visits."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from simple_module_test import inertia_headers
from simple_module_test.setup_wizard import wizard_client
from simple_module_test.tenant_client import session_client


@pytest.mark.parametrize("version", ["build", lambda: "computed"])
def test_version_headers_follow_app_config(version):
    app = FastAPI()
    app.state.sm = SimpleNamespace(inertia_config=SimpleNamespace(version=version))
    assert inertia_headers(app) == {
        "X-Inertia-Version": version() if callable(version) else version
    }


def test_app_without_inertia_has_no_version_header():
    assert inertia_headers(FastAPI()) == {}


async def test_shared_clients_default_to_current_version(app, client, authenticated_client):
    expected = inertia_headers(app)
    assert expected
    for http in (client, authenticated_client):
        assert http.headers["X-Inertia-Version"] == expected["X-Inertia-Version"]
        assert "X-Inertia" not in http.headers
    async with wizard_client(app) as http:
        assert http.headers["X-Inertia-Version"] == expected["X-Inertia-Version"]
    async with session_client(app, {}) as http:
        assert http.headers["X-Inertia-Version"] == expected["X-Inertia-Version"]
