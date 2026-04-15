"""Shared fixtures for users module API tests.

The ``app_with_users`` fixture builds a full FastAPI app via ``create_app`` but
with an in-memory SQLite database, seeded roles, and test-friendly settings
(ConsoleMailer, signup disabled by default, short secrets).

The ``unauthenticated_client`` gives a plain httpx client.
The ``admin_client`` gives a client with the existing Keycloak-shaped session
cookie (admin role) — used for admin endpoint tests until Task 8 swaps
middleware.
"""

from __future__ import annotations

import json
import uuid
from base64 import b64encode
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi_users.password import PasswordHelper
from itsdangerous import TimestampSigner
from simple_module_hosting.settings import Settings
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


@pytest.fixture
async def users_app(monkeypatch):
    """Full FastAPI app with in-memory DB, seeded roles, users module active."""
    from simple_module_hosting.app_builder import create_app

    # Patch env for UsersSettings before importing
    env = _users_env(allow_signup=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=False,
    )

    application = create_app(settings)

    # Create all tables + stamp alembic version
    await _setup_app_db(application)

    # Trigger lifespan startup
    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()

    # Seed roles
    async with application.state.db.session_factory() as session:
        from sqlalchemy import select
        from users.models import Role

        existing = (await session.execute(select(Role.name))).scalars().all()
        if "admin" not in existing:
            session.add(Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator"))
        if "user" not in existing:
            session.add(Role(id=USER_ROLE_ID, name="user", description="Standard user"))
        await session.commit()

    yield application

    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def users_app_signup(monkeypatch):
    """Like users_app but with allow_signup=True."""
    from simple_module_hosting.app_builder import create_app

    env = _users_env(allow_signup=True)
    for k, v in env.items():
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

    async with application.state.db.session_factory() as session:
        from sqlalchemy import select
        from users.models import Role

        existing = (await session.execute(select(Role.name))).scalars().all()
        if "admin" not in existing:
            session.add(Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator"))
        if "user" not in existing:
            session.add(Role(id=USER_ROLE_ID, name="user", description="Standard user"))
        await session.commit()

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
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
async def anon_client_signup(users_app_signup) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client against users_app_signup (signup enabled)."""
    transport = httpx.ASGITransport(app=users_app_signup)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as c:
        yield c


def _make_admin_session_cookie(secret_key: str) -> str:
    """Build a Starlette session cookie with Keycloak-shaped admin userinfo."""
    userinfo = {
        "sub": "test-admin-id",
        "email": "admin@example.com",
        "name": "Test Admin",
        "preferred_username": "testadmin",
        "realm_access": {"roles": ["admin"]},
    }
    session_data = {"userinfo": userinfo}
    data = b64encode(json.dumps(session_data).encode())
    signer = TimestampSigner(secret_key)
    return signer.sign(data).decode("utf-8")


@pytest.fixture
async def admin_client(users_app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Client with admin Keycloak-shaped session cookie."""
    cookie = _make_admin_session_cookie(str(users_app.state.settings.secret_key))
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
            await session.execute(select(Role).where(Role.name.in_(role_names)))
        ).scalars().all()
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
