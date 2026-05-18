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
from simple_module_test import forge_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID


@pytest.fixture(autouse=True)
def _isolate_users_env(monkeypatch):
    """Scrub stale ``SM_USERS_*`` env vars from the shell/.env.

    After the env→DB migration ``UsersSettings()`` no longer reads these
    values, so this is belt-and-braces: it keeps old shell exports from
    muddying any ``SM_ENVIRONMENT`` checks or from being misread during
    developer spelunking.
    """
    for key in list(os.environ):
        if key.startswith("SM_USERS_"):
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _users_overrides(allow_signup: bool = False) -> dict[str, tuple[str, str]]:
    """Values seeded into the ``SettingsStore`` before the app lifespan runs."""
    return {
        "allow_signup": (str(allow_signup).lower(), "bool"),
        "mailer": ("console", "string"),
        "base_url": ("http://testserver", "string"),
        "cookie_secure": ("false", "bool"),
        # 32+ bytes to clear pyjwt's InsecureKeyLengthWarning for HMAC-SHA256.
        "reset_password_token_secret": ("test-reset-secret-32-bytes-xxxxx", "string"),
        "verification_token_secret": ("test-verify-secret-32-bytes-xxxxx", "string"),
        "login_rate_limit_failures": ("5", "int"),
        "login_rate_limit_window_seconds": ("300", "int"),
        "login_rate_limit_cooldown_seconds": ("900", "int"),
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


async def _seed_users_settings(application, *, allow_signup: bool) -> None:
    """Write the test UsersSettings overrides to the DB before hydrate runs.

    Hydrate fires inside the lifespan ``__aenter__``, so this needs to land
    between table creation and lifespan entry.
    """
    from settings.service import SettingService
    from settings.store import SettingsStore

    async with application.state.sm.db.session_factory() as session:
        store = SettingsStore(SettingService(session))
        for field, (raw, vtype) in _users_overrides(allow_signup=allow_signup).items():
            await store.set_override("users", field, raw, vtype)
        await session.commit()


async def _build_users_app(monkeypatch, *, allow_signup: bool):
    """Build a test FastAPI app with DB created, settings seeded, lifespan started."""
    from simple_module_hosting.app_builder import create_app

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=False,
    )
    application = create_app(settings)
    await _setup_app_db(application)
    await _seed_users_settings(application, allow_signup=allow_signup)

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


async def _make_standard_user(app, email: str = "user@example.com"):
    """Seed a non-admin User with the standard ``user`` role.

    Used by the negative-authz tests to confirm endpoints protected by
    ``RequiresPermission(...)`` reject authenticated-but-non-admin callers.
    """
    from users.bootstrap import create_standard_user
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        result = await create_standard_user(
            session,
            email=email,
            password="UserPass1!",
            full_name="Regular User",
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


@pytest.fixture
async def user_client(users_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Client with a signed session cookie for an authenticated non-admin user.

    Counterpart to ``admin_client`` — every endpoint behind
    ``RequiresPermission(...)`` should answer with 403 for this caller, since
    the default role map only grants the wildcard to ``admin``.
    """
    user = await _make_standard_user(users_app)
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
