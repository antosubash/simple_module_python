"""Root conftest — shared fixtures available to all test directories."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from simple_module_hosting.settings import Settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture
def settings() -> Settings:
    """Settings configured for testing with in-memory SQLite."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
        keycloak_url="http://localhost:8080",
        keycloak_realm="test-realm",
        keycloak_client_id="test-client",
        keycloak_client_secret="test-secret",
    )


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a fresh in-memory async SQLite engine."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session backed by in-memory SQLite."""
    from sm_products.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def app(settings: Settings):
    """Create a FastAPI app with tables pre-created."""
    from simple_module_hosting.app_builder import create_app

    application = create_app(settings)

    from sm_products.models import Base as ProductsBase

    engine = application.state.db.engine
    async with engine.begin() as conn:
        await conn.run_sync(ProductsBase.metadata.create_all)

    yield application

    await application.state.db.engine.dispose()


@pytest.fixture
async def client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated async HTTP client."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def authenticated_client(app) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Authenticated async HTTP client (admin user via signed session cookie)."""
    import json
    from base64 import b64encode

    from itsdangerous import TimestampSigner

    userinfo = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "name": "Test User",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["admin"]},
    }
    session_data = {"userinfo": userinfo}
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
