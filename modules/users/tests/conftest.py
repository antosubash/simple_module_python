"""Shared fixtures for users module API tests.

The ``users_app`` fixture builds a full FastAPI app via ``create_app`` but
with an in-memory SQLite database, seeded roles, and test-friendly settings
(ConsoleMailer, signup disabled by default, short secrets).

The ``anon_client`` gives a plain httpx client.
The ``admin_client`` gives a client with a signed local-user session cookie
carrying a real admin User row (written into the in-memory DB).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi_users.password import PasswordHelper
from simple_module_hosting.csrf import SESSION_CSRF_TOKEN_KEY
from simple_module_hosting.settings import Settings
from simple_module_testing import forge_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID

# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _users_env(allow_signup: bool = False) -> dict:
    return {
        "SM_USERS_ALLOW_SIGNUP": str(allow_signup).lower(),
        "SM_USERS_MAILER": "console",
        "SM_USERS_BASE_URL": "http://testserver",
        "SM_USERS_COOKIE_SECURE": "false",
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET": "test-reset-secret-32-bytes-xxxx",
        "SM_USERS_VERIFICATION_TOKEN_SECRET": "test-verify-secret-32-bytes-xxxx",
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
    from simple_module_hosting._migrations import resolve_head_revision
    from sqlalchemy import text

    head = resolve_head_revision()

    async with application.state.db.engine.begin() as conn:

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

    async with application.state.db.session_factory() as session:
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


_TEST_CSRF_TOKEN = "test-csrf-token"


@pytest.fixture
async def anon_client(users_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against users_app.

    Pre-seeded with a signed anonymous session that carries a CSRF token and a
    matching ``X-CSRF-Token`` header, so POST flows (login, accept-invite, etc.)
    pass validation without first making a GET to mint a token."""
    cookie = forge_session_cookie(
        str(users_app.state.settings.secret_key),
        {SESSION_CSRF_TOKEN_KEY: _TEST_CSRF_TOKEN},
    )
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _TEST_CSRF_TOKEN},
    ) as c:
        yield c


@pytest.fixture
async def anon_client_signup(users_app_signup) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against users_app_signup (signup enabled)."""
    cookie = forge_session_cookie(
        str(users_app_signup.state.settings.secret_key),
        {SESSION_CSRF_TOKEN_KEY: _TEST_CSRF_TOKEN},
    )
    transport = httpx.ASGITransport(app=users_app_signup)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _TEST_CSRF_TOKEN},
    ) as c:
        yield c


async def _make_admin_user(app):
    """Seed an admin User + Role into app's DB and return the User row."""
    from users.bootstrap import create_admin
    from users.models import User

    async with app.state.db.session_factory() as session:
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
    """Client with a signed local-user session cookie (admin role) and CSRF token."""
    user = await _make_admin_user(users_app)
    cookie = forge_session_cookie(
        str(users_app.state.settings.secret_key),
        {"user_id": str(user.id), SESSION_CSRF_TOKEN_KEY: _TEST_CSRF_TOKEN},
    )
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": cookie},
        headers={"X-CSRF-Token": _TEST_CSRF_TOKEN},
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# DB session fixture scoped to users_app
# ---------------------------------------------------------------------------


@pytest.fixture
async def users_db(users_app) -> AsyncGenerator[AsyncSession, None]:
    """Session against the users_app in-memory DB."""
    async with users_app.state.db.session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Password helper
# ---------------------------------------------------------------------------

_pw_helper = PasswordHelper()


def hash_password(plain: str) -> str:
    return _pw_helper.hash(plain)


# ---------------------------------------------------------------------------
# User creation helpers
# ---------------------------------------------------------------------------


async def create_verified_user(
    session: AsyncSession,
    email: str = "user@example.com",
    password: str = "SecurePass1!",
    full_name: str | None = "Test User",
    role_names: list[str] | None = None,
) -> object:
    from users.models import Role, User, UserRole

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=False,
        is_verified=True,
        full_name=full_name,
    )
    session.add(user)
    await session.flush()

    if role_names:
        from sqlalchemy import select

        roles = (
            (await session.execute(select(Role).where(Role.name.in_(role_names)))).scalars().all()
        )
        for role in roles:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    await session.commit()
    await session.refresh(user)
    return user


async def create_unverified_user(
    session: AsyncSession,
    email: str = "unverified@example.com",
    password: str = "SecurePass1!",
) -> object:
    from users.models import User

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        is_superuser=False,
        is_verified=False,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# Fixtures consumed by the users.middleware unit tests live in
# _middleware_support.py (imported as a pytest plugin below).
pytest_plugins = ["_middleware_support"]
