"""Shared fixtures for users module API tests.

The ``users_app`` fixture builds a full FastAPI app via ``create_app`` but
with an in-memory SQLite database, seeded roles, and test-friendly settings
(ConsoleMailer, signup disabled by default, short secrets).

The ``anon_client`` gives a plain httpx client.
The ``admin_client`` gives a client with a signed local-user session cookie
carrying a real admin User row (written into the in-memory DB).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from simple_module_hosting.settings import Settings
from simple_module_testing import forge_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID


@pytest.fixture(autouse=True)
def _isolate_users_env(monkeypatch):
    """Insulate every users-module test from the repo's real ``.env``.

    Local development sets ``SM_USERS_BOOTSTRAP_EMAIL`` (and similar) in
    ``.env`` so the dev login page can offer quick-login buttons. When
    pytest runs in that checkout, pydantic-settings loads those values and
    they leak into tests asserting defaults or empty-table behavior. We
    turn off the dotenv load and scrub any leftover ``SM_USERS_*`` from
    ``os.environ``; fixtures that need specific values then set them
    explicitly via ``monkeypatch.setenv``.
    """
    from users.settings import UsersSettings

    monkeypatch.setitem(UsersSettings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("SM_USERS_"):
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _users_env(allow_signup: bool = False) -> dict:
    return {
        "SM_USERS_ALLOW_SIGNUP": str(allow_signup).lower(),
        "SM_USERS_MAILER": "console",
        "SM_USERS_BASE_URL": "http://testserver",
        "SM_USERS_COOKIE_SECURE": "false",
        # 32+ bytes to clear pyjwt's InsecureKeyLengthWarning for HMAC-SHA256.
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET": "test-reset-secret-32-bytes-xxxxx",
        "SM_USERS_VERIFICATION_TOKEN_SECRET": "test-verify-secret-32-bytes-xxxxx",
        "SM_USERS_LOGIN_RATE_LIMIT_FAILURES": "5",
        "SM_USERS_LOGIN_RATE_LIMIT_WINDOW_SECONDS": "300",
        "SM_USERS_LOGIN_RATE_LIMIT_COOLDOWN_SECONDS": "900",
    }


# ---------------------------------------------------------------------------
# Full-app fixture
# ---------------------------------------------------------------------------


async def _setup_app_db(application) -> None:
    """Create all tables and stamp alembic version so migration check passes."""

    from simple_module_db.base import all_module_bases
    from simple_module_hosting.migrations import resolve_head_revision
    from sqlalchemy import text

    head = resolve_head_revision()

    async with application.state.sm.db.engine.begin() as conn:

        def _create(sync_conn):
            for base in all_module_bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_create)

        if head:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            await conn.execute(text("DELETE FROM alembic_version"))
            await conn.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                {"v": head},
            )


async def _seed_roles(application) -> None:
    """Insert admin/user Role rows with deterministic UUIDs if missing."""
    from sqlalchemy import select
    from users.models import Role

    async with application.state.sm.db.session_factory() as session:
        existing = set((await session.execute(select(Role.name))).scalars().all())
        if "admin" not in existing:
            session.add(Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator"))
        if "user" not in existing:
            session.add(Role(id=USER_ROLE_ID, name="user", description="Standard user"))
        await session.commit()


async def _build_users_app(monkeypatch, *, allow_signup: bool):
    """Build a test FastAPI app with env patched, DB created, lifespan started."""
    from simple_module_hosting.app_builder import create_app

    for k, v in _users_env(allow_signup=allow_signup).items():
        monkeypatch.setenv(k, v)

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=False,
    )
    application = create_app(settings)
    await _setup_app_db(application)

    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()
    await _seed_roles(application)
    return application, ctx


@pytest.fixture
async def users_app(monkeypatch):
    """Full FastAPI app with in-memory DB, seeded roles, users module active."""
    application, ctx = await _build_users_app(monkeypatch, allow_signup=False)
    yield application
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def users_app_signup(monkeypatch):
    """Like users_app but with allow_signup=True."""
    application, ctx = await _build_users_app(monkeypatch, allow_signup=True)
    yield application
    await ctx.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def anon_client(users_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against users_app."""
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
async def anon_client_signup(users_app_signup) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against users_app_signup (signup enabled)."""
    transport = httpx.ASGITransport(app=users_app_signup)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as c:
        yield c


async def _make_admin_user(app):
    """Seed an admin User + Role into app's DB and return the User row."""
    from users.bootstrap import create_admin
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        result = await create_admin(
            session,
            email="admin@example.com",
            password="AdminPass1!",
            full_name="Test Admin",
        )
    user: User = result.user
    return user


@pytest.fixture
async def admin_client(users_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Client with a signed local-user session cookie (admin role)."""
    user = await _make_admin_user(users_app)
    cookie = forge_session_cookie(
        str(users_app.state.sm.settings.secret_key),
        {"user_id": str(user.id)},
    )
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# DB session fixture scoped to users_app
# ---------------------------------------------------------------------------


@pytest.fixture
async def users_db(users_app) -> AsyncGenerator[AsyncSession, None]:
    """Session against the users_app in-memory DB."""
    async with users_app.state.sm.db.session_factory() as session:
        yield session


# Fixtures consumed by the users.middleware unit tests live in
# _middleware_support.py (imported as a pytest plugin below).
pytest_plugins = ["_middleware_support"]
