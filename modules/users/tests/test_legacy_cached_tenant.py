"""A pre-#381 session cookie's cached ``tenant_id`` is ignored.

``users_user.tenant_id`` is gone and the active tenant is resolved per request
from memberships, but cookies signed before the upgrade still carry the old
value inside ``user_ctx``. Honouring it would keep acting for a tenant the
user may have left.
"""

from __future__ import annotations

import time

import pytest
from auth.contracts.schemas import UserContext
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from sqlalchemy import select
from starlette.requests import Request
from users.models import User
from users.provider import UsersAuthProvider


async def _admin_id(users_app) -> str:
    async with users_app.state.sm.db.session_factory() as session:
        stmt = select(User.id).where(User.email == "admin@example.com")
        return str((await session.execute(stmt)).scalar_one())


@pytest.mark.anyio
async def test_old_cookie_tenant_id_is_dropped_on_the_cached_path(users_app):
    user_id = await _admin_id(users_app)
    legacy_ctx = UserContext(
        id=user_id, email="admin@example.com", name="Admin", roles=["admin"], tenant_id="acme"
    ).to_session_dict()
    session = {
        "user_id": user_id,
        "user_ctx": legacy_ctx,
        "session_version": 0,
        SESSION_EXPIRES_AT_KEY: int(time.time()) + 3600,
    }
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": users_app,
        "session": session,
    }

    ctx = await UsersAuthProvider().resolve_user(Request(scope))

    assert ctx is not None
    assert ctx.id == user_id
    assert ctx.name == "Admin"  # the cached context was used, not a DB reload
    assert ctx.tenant_id is None
