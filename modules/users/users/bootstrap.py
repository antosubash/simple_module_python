"""Shared admin-creation logic used by the CLI and env-var auto-bootstrap."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from users.constants import ADMIN_ROLE_ID, USER_ROLE_ID
from users.models import Role, User, UserRole
from users.settings import UsersSettings

logger = logging.getLogger("users.bootstrap")


@dataclass
class CreateAdminResult:
    user: User
    created: bool  # False when admin already existed and we just ensured the role


async def create_admin(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    force: bool = False,
) -> CreateAdminResult:
    """Create or update an admin user. Idempotent by default.

    - If no user with this email exists: create one with is_active=True,
      is_verified=True, is_superuser=True; hash the password; ensure the
      'admin' Role row exists (create from ADMIN_ROLE_ID if missing);
      insert UserRole.
    - If the user exists and force=True: update the password and ensure the
      admin role is attached.
    - If the user exists and force=False: return created=False without
      changing the password.
    """
    # Use a lazy import so this module has no import-time dependency on
    # fastapi-users (which lets tooling introspect it even in minimal envs).
    from fastapi_users.password import PasswordHelper

    existing = (
        await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()

    # Look up by name first (works on both Postgres and SQLite regardless of UUID
    # storage format), then fall back to id-based lookup in case name was changed.
    admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()  # ty:ignore[invalid-argument-type]
    if admin_role is None:
        admin_role = (
            await db.execute(select(Role).where(Role.id == ADMIN_ROLE_ID))  # ty:ignore[invalid-argument-type]
        ).scalar_one_or_none()
    if admin_role is None:
        # The seed migration (e3ce9754e6dc) inserts this row, so in a real
        # deployment we should never hit this branch. Kept as a safety net for
        # tests (where `create_all` runs without data migrations) and for
        # scenarios where someone ran `alembic downgrade` past the seed
        # revision but not past the schema revision.
        admin_role = Role(id=ADMIN_ROLE_ID, name="admin", description="Administrator")
        db.add(admin_role)
        await db.flush()

    hasher = PasswordHelper()
    if existing is None:
        user = User(
            email=email,
            hashed_password=hasher.hash(password),
            is_active=True,
            is_verified=True,
            is_superuser=True,
            full_name=full_name,
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        await db.commit()
        await db.refresh(user)
        logger.info("users.bootstrap.created", extra={"email": email, "id": str(user.id)})
        return CreateAdminResult(user=user, created=True)

    if force:
        existing.hashed_password = hasher.hash(password)
        existing.is_active = True
        existing.is_verified = True
        existing.is_superuser = True
        if full_name is not None:
            existing.full_name = full_name
        existing_link = (
            await db.execute(
                select(UserRole).where(
                    UserRole.user_id == existing.id, UserRole.role_id == admin_role.id  # ty:ignore[invalid-argument-type]
                )
            )
        ).scalar_one_or_none()
        if existing_link is None:
            db.add(UserRole(user_id=existing.id, role_id=admin_role.id))
        await db.commit()
        logger.info(
            "users.bootstrap.updated",
            extra={"email": email, "id": str(existing.id)},
        )
        return CreateAdminResult(user=existing, created=False)

    logger.info("users.bootstrap.noop", extra={"email": email, "id": str(existing.id)})
    return CreateAdminResult(user=existing, created=False)


async def create_standard_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> CreateAdminResult:
    """Create a non-admin user with the 'user' role. Idempotent (noop if exists).

    Unlike ``create_admin`` this is not meant to be called from the CLI — it's
    used by the env-var bootstrap to seed a second account for dev/testing.
    """
    from fastapi_users.password import PasswordHelper

    existing = (
        await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("users.bootstrap.user_noop", extra={"email": email, "id": str(existing.id)})
        return CreateAdminResult(user=existing, created=False)

    user_role = (await db.execute(select(Role).where(Role.name == "user"))).scalar_one_or_none()  # ty:ignore[invalid-argument-type]
    if user_role is None:
        user_role = (
            await db.execute(select(Role).where(Role.id == USER_ROLE_ID))  # ty:ignore[invalid-argument-type]
        ).scalar_one_or_none()
    if user_role is None:
        # Safety net — the seed migration normally inserts this row.
        user_role = Role(id=USER_ROLE_ID, name="user", description="Standard user")
        db.add(user_role)
        await db.flush()

    user = User(
        email=email,
        hashed_password=PasswordHelper().hash(password),
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=full_name,
    )
    db.add(user)
    await db.flush()
    db.add(UserRole(user_id=user.id, role_id=user_role.id))
    await db.commit()
    await db.refresh(user)
    logger.info("users.bootstrap.user_created", extra={"email": email, "id": str(user.id)})
    return CreateAdminResult(user=user, created=True)


async def _user_table_is_empty(db: AsyncSession) -> bool:
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return count == 0


async def bootstrap_admin_from_env(app: FastAPI) -> None:
    """On-startup hook: create admin from env vars iff users table is empty.

    Reads ``SM_USERS_BOOTSTRAP_EMAIL`` + ``SM_USERS_BOOTSTRAP_PASSWORD`` via
    `UsersSettings`. If either is blank, returns silently. If the table
    already has users, returns silently (so restarts don't try to re-bootstrap).

    Optionally also creates a non-admin user from
    ``SM_USERS_BOOTSTRAP_USER_EMAIL`` + ``SM_USERS_BOOTSTRAP_USER_PASSWORD`` —
    useful in dev for testing non-admin flows alongside the admin account.
    """
    settings: UsersSettings = app.state.users_settings
    if not settings.bootstrap_email or not settings.bootstrap_password:
        return

    session_factory = app.state.db.session_factory
    async with session_factory() as session:
        if not await _user_table_is_empty(session):
            logger.debug("users.bootstrap.skipped (users table non-empty)")
            return

        try:
            await create_admin(
                session,
                email=settings.bootstrap_email,
                password=settings.bootstrap_password,
            )
            if settings.bootstrap_user_email and settings.bootstrap_user_password:
                await create_standard_user(
                    session,
                    email=settings.bootstrap_user_email,
                    password=settings.bootstrap_user_password,
                )
        except Exception:
            logger.exception("users.bootstrap.failed")
            raise
