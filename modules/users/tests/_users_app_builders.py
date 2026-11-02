"""App-construction helpers for the users test fixtures.

Split out of ``conftest.py`` so that file holds fixtures and this one holds
the machinery they call: schema creation, seed data, and the ``create_app``
wiring. Not named ``test_*`` so pytest does not collect it.
"""

from __future__ import annotations

import httpx
from simple_module_hosting.settings import Settings
from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID

ALICE = "alice@example.com"

# ---------------------------------------------------------------------------


def _users_overrides(allow_signup: bool = False) -> dict[str, tuple[str, str]]:
    """Values seeded into the ``SettingsStore`` before the app lifespan runs."""
    return {
        "allow_signup": (str(allow_signup).lower(), "bool"),
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
    from simple_module_hosting.migrations import resolve_head_revisions
    from sqlalchemy import text

    # Plural: each module's first migration sets its own branch_labels, so a
    # real upgraded database carries one alembic_version row per branch.
    # Stamping only one leaves the others looking un-applied, which reads as a
    # behind-head schema and puts every app built here behind the setup gate.
    heads = resolve_head_revisions()

    async with application.state.sm.db.engine.begin() as conn:

        def _create(sync_conn):
            for base in all_module_bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_create)

        if heads:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            await conn.execute(text("DELETE FROM alembic_version"))
            for head in heads:
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
    # Direct inserts bypass the role service that would refresh the cache; startup
    # already warmed it (with the role it seeds), so refresh like a real write would.
    from users.roles_cache import refresh_roles_cache

    await refresh_roles_cache(application)


async def _seed_users_settings(
    application, *, allow_signup: bool, overrides: dict[str, tuple[str, str]] | None = None
) -> None:
    """Write the test UsersSettings overrides to the DB before hydrate runs.

    Hydrate fires inside the lifespan ``__aenter__``, so this needs to land
    between table creation and lifespan entry.
    """
    from settings.service import SettingService
    from settings.store import SettingsStore

    async with application.state.sm.db.session_factory() as session:
        store = SettingsStore(SettingService(session))
        rows = _users_overrides(allow_signup=allow_signup) | (overrides or {})
        for field, (raw, vtype) in rows.items():
            await store.set_override("users", field, raw, vtype)
        await session.commit()


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


async def _build_users_app(
    monkeypatch,
    *,
    allow_signup: bool,
    seed_admin: bool = True,
    database_url: str = "sqlite+aiosqlite:///:memory:",
    overrides: dict[str, tuple[str, str]] | None = None,
):
    """Build a test FastAPI app with DB created, settings seeded, lifespan started.

    ``database_url`` lets several apps share one SQLite file, standing in for
    workers of one deployment; ``overrides`` adds ``UsersSettings`` rows.
    """
    from simple_module_hosting.app_builder import create_app

    settings = Settings(
        database_url=database_url,
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=False,
        # Explicit: a developer's .env pointing at the shared Redis would make
        # login-lockout counters outlive the test that wrote them.
        redis_url=None,
    )
    application = create_app(settings)
    await _setup_app_db(application)
    await _seed_users_settings(application, allow_signup=allow_signup, overrides=overrides)

    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()
    await _seed_roles(application)
    # SetupMiddleware redirects everything to /setup until an administrator
    # exists. These tests assert on ordinary pages, not on first-run setup, so
    # the app has to model a configured install. Reuses the same admin
    # admin_client seeds — create_admin is idempotent, so that fixture's own
    # call still resolves the id without creating a second account.
    if seed_admin:
        await _make_admin_user(application)
    return application, ctx


# ---------------------------------------------------------------------------
# Request and row helpers for the login-lockout tests
# ---------------------------------------------------------------------------


def _client(app, ip: str) -> httpx.AsyncClient:
    """A client whose requests arrive from *ip*."""
    transport = httpx.ASGITransport(app=app, client=(ip, 1))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _login(app, ip: str, username: str, password: str = "wrong") -> httpx.Response:
    async with _client(app, ip) as c:
        return await c.post(
            "/api/users/auth/login", data={"username": username, "password": password}
        )


async def user_row(app, email: str):
    """The ``User`` row for *email*, or ``None``, read in a fresh session."""
    from sqlalchemy import select
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
