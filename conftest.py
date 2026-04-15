"""Root conftest — shared fixtures available to all test directories."""

from __future__ import annotations

import contextlib
import importlib
from collections.abc import AsyncGenerator
from functools import lru_cache

import httpx
import pytest
from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases
from simple_module_db.session import DatabaseState, init_db
from simple_module_hosting.settings import Settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
)


@pytest.fixture
def settings() -> Settings:
    """Settings configured for testing with in-memory SQLite.

    Multi-tenancy stays on so the existing ``TenantMiddleware`` tests
    (and the ``X-Tenant-ID`` header paths they rely on) keep working.
    Individual tests that want the tenant middleware absent construct
    their own ``Settings(multi_tenant=False, ...)`` in the test body.
    """
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=True,
        tenant_header="X-Tenant-ID",
    )


@pytest.fixture
async def db_state() -> AsyncGenerator[DatabaseState, None]:
    """Create a fresh in-memory DatabaseState with listeners registered."""
    from simple_module_db.listeners import register_listeners

    state = init_db("sqlite+aiosqlite:///:memory:")
    register_listeners(state)
    yield state
    await state.engine.dispose()


@pytest.fixture
async def engine(db_state: DatabaseState) -> AsyncEngine:
    """Return the engine from the test DatabaseState."""
    return db_state.engine


@lru_cache(maxsize=1)
def _ensure_models_imported() -> list:
    """Import all module models so all_module_bases is populated (cached)."""
    for mod in discover_modules():
        pkg = type(mod).__module__.split(".")[0]
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{pkg}.models")
    return list(all_module_bases)


@lru_cache(maxsize=1)
def _alembic_head() -> str | None:
    """Cached head revision — cannot change within a pytest run."""
    from simple_module_hosting._migrations import resolve_head_revision

    return resolve_head_revision()


async def _create_all_tables(engine) -> None:
    """Create all module tables in a single connection.

    Also stamps the alembic_version table at head so the app's startup
    migration check (``check_migrations``) treats the test DB as current.
    Without the stamp the check would raise because ``create_all`` doesn't
    touch alembic_version.
    """
    from sqlalchemy import text

    bases = _ensure_models_imported()
    head = _alembic_head()

    async with engine.begin() as conn:

        def _sync_create_all(sync_conn):
            for base in bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_sync_create_all)

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
async def db_session(db_state: DatabaseState) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session backed by in-memory SQLite."""
    await _create_all_tables(db_state.engine)

    async with db_state.session_factory() as session:
        yield session


@pytest.fixture
async def app(settings: Settings):
    """Create a FastAPI app with tables pre-created and lifespan triggered."""
    from simple_module_hosting.app_builder import create_app

    application = create_app(settings)

    await _create_all_tables(application.state.db.engine)

    # Trigger lifespan startup so app.state.migration is populated
    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()

    yield application

    # Lifespan shutdown disposes the engine
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated async HTTP client."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def authenticated_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTPX client with a signed session cookie carrying a seeded admin user's id."""
    import json
    from base64 import b64encode

    from itsdangerous import TimestampSigner
    from users.bootstrap import create_admin

    async with app.state.db.session_factory() as session:
        result = await create_admin(
            session,
            email="admin@test",
            password="test-password",
            full_name="Test Admin",
        )
        user_id = str(result.user.id)

    session_data = {"user_id": user_id}
    data = b64encode(json.dumps(session_data).encode())
    signer = TimestampSigner(str(app.state.settings.secret_key))
    signed = signer.sign(data).decode("utf-8")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": signed},
    ) as c:
        yield c
