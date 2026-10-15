"""Fixtures for the api_tokens tests: signed-in actors and bearer calls."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
import pytest
from _api_tokens_support import CSRF, Actor, join_tenant, make_admin
from simple_module_test.tenant_client import create_user, session_client


@pytest.fixture
def actor(app) -> Callable[..., AbstractAsyncContextManager[Actor]]:
    """``async with actor(admin=True) as a:`` — a signed-in user with a tenant.

    The session carries a known CSRF token (``CSRF``) so mutations can echo it.
    """
    from tenants.constants import SESSION_ACTIVE_TENANT

    @asynccontextmanager
    async def factory(
        *, admin: bool = False, tenant_id: str | None = None
    ) -> AsyncGenerator[Actor]:
        email = f"{'admin' if admin else 'user'}-{uuid.uuid4().hex[:8]}@example.com"
        user_id = await (make_admin(app, email) if admin else create_user(app, email))
        tenant_id = await join_tenant(app, user_id, email, tenant_id)
        data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
        async with session_client(app, data) as client:
            yield Actor(client, user_id, tenant_id)

    return factory


@pytest.fixture
async def bearer(app) -> AsyncIterator[Callable[..., Any]]:
    """``await bearer("GET", url, token)`` — a cookie-less request with a bearer token."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:

        async def call(method: str, url: str, token: str, **kwargs: Any) -> httpx.Response:
            headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
            return await client.request(method, url, headers=headers, **kwargs)

        yield call
