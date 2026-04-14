"""Fixtures specific to cross-module integration tests.

The root ``conftest.py`` already exposes ``app``, ``client`` and
``authenticated_client`` (admin). This conftest adds:

* ``viewer_client`` — authenticated as a non-admin user (role ``viewer``)
  for exercising permission boundaries on write endpoints.
* ``inertia_client`` — admin client that advertises itself as an Inertia
  request so view endpoints return JSON page data.
"""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import AsyncGenerator

import httpx
import pytest
from itsdangerous import TimestampSigner


def _sign_session(secret: str, userinfo: dict) -> str:
    """Build a signed ``session`` cookie value matching SessionMiddleware."""
    data = b64encode(json.dumps({"userinfo": userinfo}).encode())
    return TimestampSigner(secret).sign(data).decode("utf-8")


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
    cookie = _sign_session(str(app.state.settings.secret_key), userinfo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as c:
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
    cookie = _sign_session(str(app.state.settings.secret_key), userinfo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
        headers={"X-Inertia": "true"},
    ) as c:
        yield c
