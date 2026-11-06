"""The users admin list costs the same number of SQL statements for 2 rows or 22.

A per-row lookup (roles, sessions, tenants) makes the count grow with the
page: the N+1 that the development ``Server-Timing`` header shows in the
browser and that ``docs/frontend/performance.md`` tells authors to pin with a
test like this one.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import FastAPI
from fastapi_users.password import PasswordHelper
from simple_module_db.query_stats import install_query_stats, track_queries
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import Role, User, UserRole

_pw = PasswordHelper()


async def _add_users(session: AsyncSession, prefix: str, count: int) -> None:
    role = (await session.execute(select(Role).where(Role.name == "admin"))).scalar_one()
    for i in range(count):
        user = User(
            id=uuid.uuid4(),
            email=f"{prefix}{i}@example.com",
            hashed_password=_pw.hash("SecurePass1!"),
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.commit()


async def _statements(app: FastAPI, client: httpx.AsyncClient) -> int:
    """The page's own statement count.

    Auth adds statements on its own schedule (loading the principal, the
    session-version check that follows it), so take the cheapest of three requests.
    """
    install_query_stats(app.state.sm.db.engine)
    counts = []
    for _ in range(3):
        with track_queries() as stats:
            resp = await client.get("/admin/users/", headers={"X-Inertia": "true"})
        assert resp.status_code == 200
        assert resp.json()["component"] == "Users/Users/Index"
        counts.append(stats.count)
    return min(counts)


async def test_list_query_count_does_not_grow_with_rows(
    users_app: FastAPI, admin_client: httpx.AsyncClient, users_db: AsyncSession
) -> None:
    await _add_users(users_db, "few", 2)
    few = await _statements(users_app, admin_client)

    await _add_users(users_db, "many", 20)
    many = await _statements(users_app, admin_client)

    assert few > 0, "statements were not counted; is the engine instrumented?"
    assert many == few
