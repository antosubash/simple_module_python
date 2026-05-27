"""Helpers + fixtures for the users.middleware unit tests.

Registered as a pytest plugin via ``pytest_plugins = ["_middleware_support"]``
in conftest.py — that way the fixtures (``_mw_seed_roles``, ``mw_active_user``)
are auto-discovered by pytest without needing imports in the test files,
which avoids F811 warnings where fixture names appear as test-function
parameters.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from simple_module_test import forge_session_cookie
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID
from auth.middleware import AuthMiddleware

SECRET_KEY = "test-secret-key-for-session-middleware"


def _session_cookie(data: dict[str, Any]) -> dict[str, str]:
    return {"session": forge_session_cookie(SECRET_KEY, data)}


async def _build_app(db_state, inner_handler=None, *, principal_resolvers=None):
    """Build a minimal ASGI app with AuthMiddleware + SessionMiddleware.

    ``principal_resolvers`` (optional) is a list of resolvers seeded onto
    ``app.state.auth.principal_resolvers`` before the middleware runs.
    Defaults to an empty registry — matches a production app where no
    downstream module has registered anything.
    """
    from auth.state import AuthState

    async def _default_handler(request: Request):
        user = getattr(request.state, "user", None)
        return JSONResponse(
            {
                "path": request.url.path,
                "user": (
                    {
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "roles": user.roles,
                        "tenant_id": user.tenant_id,
                    }
                    if user is not None
                    else None
                ),
            }
        )

    handler = inner_handler or _default_handler

    app = FastAPI()
    app.state.sm = SimpleNamespace(db=db_state)
    from users.provider import UsersAuthProvider

    app.state.auth = AuthState(
        auth_provider=UsersAuthProvider(),
        principal_resolvers=list(principal_resolvers or []),
    )

    @app.get("/{path:path}")
    async def _catch_all(request: Request, path: str = ""):
        return await handler(request)

    # Middleware is applied in reverse order: SessionMiddleware outermost.
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
    return app


@pytest.fixture
async def _mw_seed_roles(db_session):
    """Insert the standard admin/user roles for middleware tests."""
    from users.models import Role

    db_session.add_all(
        [
            Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator"),
            Role(id=USER_ROLE_ID, name="user", description="Standard user"),
        ]
    )
    await db_session.commit()


@pytest.fixture
async def mw_active_user(db_session, _mw_seed_roles):
    """Active user with the 'admin' role — used by the middleware tests."""
    from users.models import User, UserRole

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="middleware-test@example.com",
        hashed_password="hashed",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        full_name="Middleware Tester",
        tenant_id="acme",
    )
    link = UserRole(user_id=user_id, role_id=ADMIN_ROLE_ID)
    db_session.add_all([user, link])
    await db_session.commit()
    return user
