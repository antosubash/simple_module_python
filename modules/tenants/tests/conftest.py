"""Helpers: real users with their own signed-session clients.

``tenant_client`` (a member of a tenant, with a role) comes from the
``simple_module_test`` plugin; ``user_client`` here is a user with *no* tenant,
which the tests that exercise creating and joining organisations start from.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from simple_module_test.tenant_client import create_user, session_client
from tenants.resolver import forget


@pytest.fixture(autouse=True)
def _fresh_membership_cache():
    forget(None)
    yield
    forget(None)


@pytest.fixture
def user_client(app) -> Callable:
    """``async with user_client("a@x.io") as (client, user_id): ...``"""

    @asynccontextmanager
    async def factory(email: str) -> AsyncGenerator[tuple[httpx.AsyncClient, str], None]:
        user_id = await create_user(app, email)
        async with session_client(app, {"user_id": user_id}) as client:
            yield client, user_id

    return factory
