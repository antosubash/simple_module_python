"""Registration must release its connection before the durable role checkpoint."""

import asyncio

import pytest
from simple_module_hosting.settings import Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from users.constants import USER_ROLE_NAME
from users.models import Role, User, UserRole


@pytest.fixture
def settings(settings: Settings, tmp_path) -> Settings:
    database_url = settings.database_url
    if database_url.startswith("sqlite"):
        database_url = f"sqlite+aiosqlite:///{tmp_path / 'signup.db'}"
    return settings.model_copy(
        update={"database_url": database_url, "multi_tenant": False, "tenant_header": ""}
    )


async def test_signup_attaches_default_role_with_one_connection(app, client):
    # Constrain registration after startup, which has its own DB operations.
    db = app.state.sm.db
    engine = create_async_engine(db.engine.url, pool_size=1, max_overflow=0)
    await db.engine.dispose()
    db.engine = engine
    db.session_factory.configure(bind=engine)
    app.state.users.settings = app.state.users.settings.model_copy(
        update={"allow_signup": True, "require_verification": False}
    )
    email = "single-connection@example.com"

    async with asyncio.timeout(3):
        response = await client.post(
            "/api/users/auth/register", json={"email": email, "password": "SecurePass1!"}
        )

    assert response.status_code == 201, response.text
    assert response.json()["email"] == email
    async with app.state.sm.db.session_factory() as session:
        roles = (
            (
                await session.execute(
                    select(Role.name)
                    .join(UserRole, UserRole.role_id == Role.id)
                    .join(User, User.id == UserRole.user_id)
                    .where(User.email == email)
                )
            )
            .scalars()
            .all()
        )
    assert roles == [USER_ROLE_NAME]
