"""Fixtures specific to cross-module integration tests.

The root ``conftest.py`` already exposes ``app``, ``client`` and
``authenticated_client`` (admin). This conftest adds:

* ``viewer_client`` — authenticated as a non-admin user (role ``viewer``)
  for exercising permission boundaries on write endpoints.
* ``inertia_client`` — admin client that advertises itself as an Inertia
  request so view endpoints return JSON page data.
* ``create_product`` — factory that seeds a product via the admin API.
"""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from itsdangerous import TimestampSigner


def _sign_session(secret: str, userinfo: dict[str, Any]) -> str:
    """Build a signed ``session`` cookie value matching SessionMiddleware."""
    data = b64encode(json.dumps({"userinfo": userinfo}).encode())
    return TimestampSigner(secret).sign(data).decode("utf-8")


def _make_client(
    app, userinfo: dict[str, Any], *, extra_headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    cookie = _sign_session(str(app.state.settings.secret_key), userinfo)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
        headers=extra_headers or {},
    )


@pytest.fixture
async def viewer_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Authenticated client with only the ``viewer`` role (no admin, no products.*)."""
    userinfo = {
        "sub": "viewer-user-id",
        "email": "viewer@example.com",
        "name": "Viewer User",
        "preferred_username": "vieweruser",
        "realm_access": {"roles": ["viewer"]},
    }
    async with _make_client(app, userinfo) as c:
        yield c


@pytest.fixture
async def inertia_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Admin client that sends the ``X-Inertia`` header on every request."""
    userinfo = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["admin"]},
    }
    async with _make_client(app, userinfo, extra_headers={"X-Inertia": "true"}) as c:
        yield c


@pytest.fixture
def create_product(authenticated_client: httpx.AsyncClient):
    """Factory that POSTs a product via the admin API and returns its id."""

    async def _create(name: str = "Seed", price: str = "1.00") -> int:
        resp = await authenticated_client.post(
            "/api/products/", json={"name": name, "price": price}
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    return _create
