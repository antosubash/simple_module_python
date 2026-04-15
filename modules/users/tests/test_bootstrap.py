"""Tests for users.bootstrap — create_admin() and bootstrap_admin_from_env()."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from users.bootstrap import (
    CreateAdminResult,
    bootstrap_admin_from_env,
    create_admin,
)
from users.constants import ADMIN_ROLE_ID
from users.models import Role, User, UserRole
from users.settings import UsersSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_app(
    session_factory, *, bootstrap_email: str = "", bootstrap_password: str = ""
) -> SimpleNamespace:
    """Build a minimal app-like namespace for bootstrap_admin_from_env."""
    settings = UsersSettings(
        bootstrap_email=bootstrap_email,
        bootstrap_password=bootstrap_password,
        # Avoid reading .env by overriding all required fields
        reset_password_token_secret="test-secret",
        verification_token_secret="test-secret",
    )

    db = SimpleNamespace(session_factory=session_factory)
    return SimpleNamespace(
        state=SimpleNamespace(
            users_settings=settings,
            db=db,
        )
    )


# ---------------------------------------------------------------------------
# create_admin tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_admin_on_empty_table(users_db: AsyncSession) -> None:
    """Fresh DB: create_admin creates user + role + UserRole; result.created=True."""
    # Remove seeded roles so create_admin must create the admin role itself
    await users_db.execute(__import__("sqlalchemy").delete(UserRole))
    await users_db.execute(__import__("sqlalchemy").delete(Role))
    await users_db.commit()

    result = await create_admin(
        users_db,
        email="admin@test.example",
        password="StrongPass1!",
        full_name="Bootstrap Admin",
    )

    assert isinstance(result, CreateAdminResult)
    assert result.created is True
    assert result.user.email == "admin@test.example"
    assert result.user.is_active is True
    assert result.user.is_verified is True
    assert result.user.is_superuser is True
    assert result.user.full_name == "Bootstrap Admin"

    # Verify the user is in the DB
    user_row = (
        await users_db.execute(select(User).where(User.email == "admin@test.example"))
    ).scalar_one_or_none()
    assert user_row is not None

    # Verify the UserRole link exists
    link = (
        await users_db.execute(
            select(UserRole).where(
                UserRole.user_id == result.user.id, UserRole.role_id == ADMIN_ROLE_ID
            )
        )
    ).scalar_one_or_none()
    assert link is not None

    # Verify the admin role exists
    role = (
        await users_db.execute(select(Role).where(Role.id == ADMIN_ROLE_ID))
    ).scalar_one_or_none()
    assert role is not None
    assert role.name == "admin"


@pytest.mark.asyncio
async def test_create_admin_is_idempotent(users_db: AsyncSession) -> None:
    """Calling create_admin twice with same email returns created=False on second call."""
    first = await create_admin(
        users_db,
        email="admin2@test.example",
        password="FirstPass1!",
    )
    assert first.created is True
    original_hash = first.user.hashed_password

    second = await create_admin(
        users_db,
        email="admin2@test.example",
        password="DifferentPass1!",
    )
    assert second.created is False
    # Password must NOT have changed
    assert second.user.hashed_password == original_hash


@pytest.mark.asyncio
async def test_create_admin_force_resets_password(users_db: AsyncSession) -> None:
    """With force=True, the password is updated and created=False."""
    first = await create_admin(
        users_db,
        email="admin3@test.example",
        password="OriginalPass1!",
    )
    original_hash = first.user.hashed_password

    result = await create_admin(
        users_db,
        email="admin3@test.example",
        password="NewPass99!",
        force=True,
    )

    assert result.created is False
    # Retrieve fresh from DB to confirm the hash was persisted
    updated = (
        await users_db.execute(select(User).where(User.email == "admin3@test.example"))
    ).scalar_one()
    assert updated.hashed_password != original_hash
    # New password must verify
    helper = PasswordHelper()
    verified, _ = helper.verify_and_update("NewPass99!", updated.hashed_password)
    assert verified


@pytest.mark.asyncio
async def test_create_admin_creates_role_if_missing(users_db: AsyncSession) -> None:
    """If the admin Role row is absent, create_admin seeds it with ADMIN_ROLE_ID."""
    from sqlalchemy import delete

    # Wipe UserRole first (FK constraint), then Role
    await users_db.execute(delete(UserRole))
    await users_db.execute(delete(Role).where(Role.id == ADMIN_ROLE_ID))
    await users_db.commit()

    result = await create_admin(
        users_db,
        email="admin4@test.example",
        password="SomePass1!",
    )

    assert result.created is True
    role = (
        await users_db.execute(select(Role).where(Role.id == ADMIN_ROLE_ID))
    ).scalar_one_or_none()
    assert role is not None
    assert role.id == ADMIN_ROLE_ID


# ---------------------------------------------------------------------------
# bootstrap_admin_from_env tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_from_env_noop_when_unset(users_app) -> None:
    """bootstrap_admin_from_env does nothing when bootstrap_email is empty."""
    from sqlalchemy import select

    fake_app = _make_fake_app(
        users_app.state.db.session_factory,
        bootstrap_email="",
        bootstrap_password="",
    )
    # Patch fake_app.state onto a real app-like object
    await bootstrap_admin_from_env(fake_app)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type]

    # No users should have been created
    async with users_app.state.db.session_factory() as s:
        count = (await s.execute(select(User))).scalars().all()
    assert len(count) == 0


@pytest.mark.asyncio
async def test_bootstrap_from_env_noop_when_table_nonempty(users_app) -> None:
    """bootstrap_admin_from_env skips creation when the users table has rows."""
    from sqlalchemy import select

    # Seed a dummy user first
    async with users_app.state.db.session_factory() as s:
        dummy = User(
            email="existing@test.example",
            hashed_password=PasswordHelper().hash("dummy"),
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        s.add(dummy)
        await s.commit()

    fake_app = _make_fake_app(
        users_app.state.db.session_factory,
        bootstrap_email="admin@test.example",
        bootstrap_password="AdminPass1!",
    )
    await bootstrap_admin_from_env(fake_app)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type]

    # Only the original dummy user should exist
    async with users_app.state.db.session_factory() as s:
        users = (await s.execute(select(User))).scalars().all()
    assert len(users) == 1
    assert users[0].email == "existing@test.example"


@pytest.mark.asyncio
async def test_bootstrap_from_env_creates_admin_when_empty_and_configured(users_app) -> None:
    """bootstrap_admin_from_env creates an admin when table is empty and env vars are set."""
    from sqlalchemy import select

    fake_app = _make_fake_app(
        users_app.state.db.session_factory,
        bootstrap_email="bootstrap@test.example",
        bootstrap_password="BootPass1!",
    )
    await bootstrap_admin_from_env(fake_app)  # type: ignore[arg-type] # ty: ignore[invalid-argument-type]

    async with users_app.state.db.session_factory() as s:
        user = (
            await s.execute(select(User).where(User.email == "bootstrap@test.example"))
        ).scalar_one_or_none()

    assert user is not None
    assert user.is_superuser is True
    assert user.is_verified is True
    assert user.is_active is True
