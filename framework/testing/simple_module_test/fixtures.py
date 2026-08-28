"""Headline app/db/client fixtures shipped by the pytest plugin.

These are the fixtures the README advertises — ``settings``, ``db_state``,
``engine``, ``db_session``, ``app``, ``client``, ``authenticated_client`` —
made available to any test run in an environment that installs
``simple_module_test`` (the ``pytest11`` entry point re-exports them from
:mod:`simple_module_test.plugin`). They build a real ``create_app`` against an
in-memory SQLite DB with every installed module's tables created and the
``alembic_version`` row stamped at head, so the boot-time migration check
passes.

Module-scope imports here reference only framework packages
(``simple_module_core`` / ``simple_module_db`` / ``simple_module_hosting``),
which are this package's declared dependencies. The one plugin-module coupling
— ``authenticated_client`` seeding an admin via ``users.bootstrap`` — is a lazy
import inside the fixture body, so importing this module never requires the
``users`` module to be installed (mirroring ``plugin._bootstrap_eager_celery``,
which soft-imports ``background_tasks``).
"""

from __future__ import annotations

import contextlib
import importlib
import os
from collections.abc import AsyncGenerator, Iterator
from functools import lru_cache

import httpx
import pytest
from simple_module_core.discovery import DEFAULT_AUTH_PROVIDER, discover_modules
from simple_module_db.base import all_module_bases
from simple_module_db.session import DatabaseState, init_db
from simple_module_hosting.settings import Settings
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from simple_module_test.session_cookie import forge_session_cookie

_AUTH_PROVIDER_ENV = "SM_AUTH_PROVIDER"


@pytest.fixture(scope="session", autouse=True)
def pinned_auth_provider() -> Iterator[str]:
    """Pin ``SM_AUTH_PROVIDER`` to the local-account provider for the suite.

    ``Settings`` reads the repo's ``.env``, and the README tells anyone running
    Keycloak locally to put ``SM_AUTH_PROVIDER=keycloak`` there. Nearly every
    test that boots an app expects the ``users`` provider — ``/users/login``,
    the admin pages, the seeded admin in ``authenticated_client`` — and the
    ``Settings(...)`` construction sites are spread across module conftests,
    so pinning it on each one would be a losing game.

    The real environment outranks ``.env`` in pydantic-settings, so setting it
    here covers every construction site at once. A test that wants a different
    provider can still ``monkeypatch.setenv`` or pass ``auth_provider=`` to
    ``Settings`` directly.
    """
    previous = os.environ.get(_AUTH_PROVIDER_ENV)
    os.environ[_AUTH_PROVIDER_ENV] = DEFAULT_AUTH_PROVIDER
    try:
        yield DEFAULT_AUTH_PROVIDER
    finally:
        if previous is None:
            os.environ.pop(_AUTH_PROVIDER_ENV, None)
        else:
            os.environ[_AUTH_PROVIDER_ENV] = previous


@pytest.fixture
def settings() -> Settings:
    """Settings configured for testing with in-memory SQLite.

    Multi-tenancy stays on so the existing ``TenantMiddleware`` tests
    (and the ``X-Tenant-ID`` header paths they rely on) keep working.
    Individual tests that want the tenant middleware absent construct
    their own ``Settings(multi_tenant=False, ...)`` in the test body.

    ``auth_provider`` is pinned for the same reason as the rest: a developer
    running Keycloak locally has ``SM_AUTH_PROVIDER=keycloak`` in ``.env``,
    which would otherwise swap the auth provider out from under every test
    that expects ``/users/login``.
    """
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        multi_tenant=True,
        tenant_header="X-Tenant-ID",
        auth_provider="users",
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
def _alembic_heads() -> tuple[str, ...]:
    """Cached head revisions — cannot change within a pytest run.

    Plural: each module's first migration sets its own ``branch_labels``, so
    the history has one head per module and a real upgraded database carries
    an ``alembic_version`` row for each. Stamping only one leaves the rest
    looking un-applied, which now reads as a behind-head schema and puts every
    test app behind the setup gate.
    """
    from simple_module_hosting.migrations import resolve_head_revisions

    return resolve_head_revisions()


async def _create_all_tables(engine) -> None:
    """Create all module tables in a single connection.

    Also stamps the alembic_version table at heads so the app's startup
    migration check (``check_migrations``) treats the test DB as current.
    Without the stamp the check would raise because ``create_all`` doesn't
    touch alembic_version.
    """
    from sqlalchemy import text

    bases = _ensure_models_imported()
    heads = _alembic_heads()

    async with engine.begin() as conn:

        def _sync_create_all(sync_conn):
            for base in bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_sync_create_all)

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


@pytest.fixture
async def db_session(db_state: DatabaseState) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session backed by in-memory SQLite."""
    await _create_all_tables(db_state.engine)

    async with db_state.session_factory() as session:
        yield session


SETUP_ADMIN_EMAIL = "admin@test"
SETUP_ADMIN_PASSWORD = "test-password"


async def _seed_setup_admin(application) -> None:
    """Make the ``app`` fixture model a *configured* install.

    ``SetupMiddleware`` redirects every request to ``/setup`` until an
    administrator exists. That is right for a fresh deployment and wrong for a
    suite asserting on ordinary pages — without this, every test using ``app``
    gets a 302.

    Seeds the same admin ``authenticated_client`` uses, so that fixture's own
    ``create_admin`` call stays idempotent rather than creating a second one.

    Skipped when the ``users`` module isn't installed: an install with no
    local-accounts provider registers no setup step and is never gated, so
    there is nothing to satisfy. Use ``setup_pending_app`` to exercise the gate.
    """
    try:
        from users.bootstrap import create_admin
    except ImportError:
        return

    async with application.state.sm.db.session_factory() as session:
        await create_admin(
            session,
            email=SETUP_ADMIN_EMAIL,
            password=SETUP_ADMIN_PASSWORD,
            full_name="Test Admin",
        )


async def _build_app(settings: Settings, *, seed_admin: bool):
    from simple_module_hosting.app_builder import create_app

    application = create_app(settings)

    await _create_all_tables(application.state.sm.db.engine)
    if seed_admin:
        await _seed_setup_admin(application)

    # Trigger lifespan startup so app.state.migration is populated
    ctx = application.router.lifespan_context(application)
    await ctx.__aenter__()

    yield application

    # Lifespan shutdown disposes the engine
    await ctx.__aexit__(None, None, None)


@pytest.fixture
async def app(settings: Settings):
    """A configured app: tables created, an admin seeded, lifespan triggered."""
    async for application in _build_app(settings, seed_admin=True):
        yield application


@pytest.fixture
async def setup_pending_app(settings: Settings):
    """An app with no administrator, so the first-run setup gate is engaged.

    The counterpart to ``app``: use this to assert on setup-mode behaviour.
    """
    async for application in _build_app(settings, seed_admin=False):
        yield application


@pytest.fixture
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated async HTTP client."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
async def authenticated_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTPX client with a signed session cookie carrying a seeded admin user's id.

    Requires the ``users`` module to be installed — it seeds the admin via
    ``users.bootstrap.create_admin``. The import is deferred to here (not module
    scope) so this plugin imports cleanly without ``users``; a consumer app that
    uses this fixture without ``users`` gets a clear ImportError naming it.
    """
    from users.bootstrap import create_admin

    async with app.state.sm.db.session_factory() as session:
        # Idempotent: the `app` fixture already seeded this same admin so the
        # setup gate would release. This resolves its id for the cookie.
        result = await create_admin(
            session,
            email=SETUP_ADMIN_EMAIL,
            password=SETUP_ADMIN_PASSWORD,
            full_name="Test Admin",
        )
        user_id = str(result.user.id)

    signed = forge_session_cookie(
        app.state.sm.settings.secret_key,
        {"user_id": user_id},
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"session": signed},
    ) as c:
        yield c
