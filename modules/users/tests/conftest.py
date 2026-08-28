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

# Bare import, not relative: tests/ has no __init__.py, so these are
# top-level modules on pytest's sys.path — same mechanism as the
# _middleware_support plugin loaded at the bottom of this file.
from _users_app_builders import (
    _build_users_app,
    _make_admin_user,
    _make_standard_user,
)
from simple_module_test import forge_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _isolate_users_env(monkeypatch):
    """Scrub stale ``SM_USERS_*`` env vars from the shell/.env.

    After the env→DB migration ``UsersSettings()`` no longer reads these
    values, so this is belt-and-braces: it keeps old shell exports from
    muddying any ``SM_ENVIRONMENT`` checks or from being misread during
    developer spelunking. Also stubs out
    ``users.bootstrap._read_dotenv_bootstrap_vars`` so the developer's local
    ``.env`` can't seed bootstrap creds into tests that exercise the resolver.
    """
    from users import bootstrap as bootstrap_module

    for key in list(os.environ):
        if key.startswith("SM_USERS_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bootstrap_module, "_read_dotenv_bootstrap_vars", dict)


# ---------------------------------------------------------------------------
# Settings helpers


@pytest.fixture
async def users_app(monkeypatch):
    """Full FastAPI app with in-memory DB, seeded roles, users module active."""
    application, ctx = await _build_users_app(monkeypatch, allow_signup=False)
    yield application
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def users_app_empty(monkeypatch):
    """``users_app`` with no seeded administrator, so the users table starts empty.

    For DB-level tests that assert on absolute user counts or on behaviour
    when no account exists yet — bootstrap-from-env, user listing. They reach
    the app only through ``session_factory`` and never issue HTTP requests, so
    the first-run setup gate never applies to them.
    """
    application, ctx = await _build_users_app(monkeypatch, allow_signup=False, seed_admin=False)
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
