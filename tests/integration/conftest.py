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

import uuid as _uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi_users.password import PasswordHelper
from simple_module_testing import forge_session_cookie
from sqlalchemy import select


async def _seed_user_with_roles(app, email: str, role_names: list[str]):
    """Seed a User + roles into app's DB and return the User.

    If a named role doesn't exist yet, creates it with a deterministic UUID.
    """
    from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID
    from users.models import Role, User, UserRole

    _role_ids: dict[str, object] = {
        "admin": ADMIN_ROLE_ID,
        "user": USER_ROLE_ID,
    }

    async with app.state.sm.db.session_factory() as session:
        # Ensure requested roles exist.
        for name in role_names:
            existing = (
                await session.execute(select(Role).where(Role.name == name))
            ).scalar_one_or_none()
            if existing is None:
                role_id = _role_ids.get(name, _uuid.uuid4())
                session.add(Role(id=role_id, name=name, description=name.title()))
                await session.flush()

        user = User(
            id=_uuid.uuid4(),
            email=email,
            hashed_password=PasswordHelper().hash("TestPass1!"),
            is_active=True,
            is_superuser=False,
            is_verified=True,
            full_name=email.split("@")[0].title(),
        )
        session.add(user)
        await session.flush()

        if role_names:
            roles = (
                (await session.execute(select(Role).where(Role.name.in_(role_names))))
                .scalars()
                .all()
            )
            for role in roles:
                session.add(UserRole(user_id=user.id, role_id=role.id))

        await session.commit()
    return user


def _make_client(
    app, user_id: str, *, extra_headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    cookie = forge_session_cookie(
        str(app.state.sm.settings.secret_key),
        {"user_id": user_id},
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
        headers=extra_headers or {},
    )


@pytest.fixture
async def viewer_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Authenticated client with only the ``viewer`` role (no admin, no products.*)."""
    user = await _seed_user_with_roles(app, "viewer@example.com", ["viewer"])
    async with _make_client(app, str(user.id)) as c:
        yield c


@pytest.fixture
async def inertia_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Admin client that sends the ``X-Inertia`` header on every request."""
    async with _make_client(
        app,
        # Use the same admin user seeded by authenticated_client (fixture ordering
        # means it may or may not exist). Simpler: seed a fresh admin-role user.
        str((await _seed_user_with_roles(app, "inertia-admin@example.com", ["admin"])).id),
        extra_headers={"X-Inertia": "true"},
    ) as c:
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
