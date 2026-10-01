"""Helpers: real users with their own signed-session clients."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from simple_module_test.session_cookie import forge_session_cookie
from sqlalchemy import select
from tenants.resolver import forget


@pytest.fixture(autouse=True)
def _fresh_membership_cache():
    forget(None)
    yield
    forget(None)


async def _make_user(app, email: str) -> str:
    from users.models import Role, User, UserRole

    async with app.state.sm.db.session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        role = (await session.execute(select(Role).where(Role.name == "user"))).scalar_one_or_none()
        if role is not None:
            session.add(UserRole(user_id=user.id, role_id=role.id))
        await session.commit()
        return str(user.id)


@pytest.fixture
def user_client(app) -> Callable:
    """``async with user_client("a@x.io") as (client, user_id): ...``"""

    @asynccontextmanager
    async def factory(email: str) -> AsyncGenerator[tuple[httpx.AsyncClient, str], None]:
        user_id = await _make_user(app, email)
        cookie = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies={"session": cookie},
        ) as client:
            yield client, user_id

    return factory
