"""Shared admin-creation logic used by the CLI and env-var auto-bootstrap."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi_users.password import PasswordHelper
from simple_module_core.dotenv import parse_dotenv
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from users.constants import (
    ADMIN_ROLE_DESCRIPTION,
    ADMIN_ROLE_ID,
    ADMIN_ROLE_NAME,
    USER_ROLE_DESCRIPTION,
    USER_ROLE_ID,
    USER_ROLE_NAME,
)
from users.models import Role, User, UserRole
from users.settings import UsersSettings

# Maps a UsersSettings attribute to the env var that seeds it on first boot.
# Shared between the bootstrap function and the test fixture that isolates it.
BOOTSTRAP_ENV_KEYS: dict[str, str] = {
    "bootstrap_email": "SM_USERS_BOOTSTRAP_EMAIL",
    "bootstrap_password": "SM_USERS_BOOTSTRAP_PASSWORD",
    "bootstrap_user_email": "SM_USERS_BOOTSTRAP_USER_EMAIL",
    "bootstrap_user_password": "SM_USERS_BOOTSTRAP_USER_PASSWORD",
}

logger = logging.getLogger("users.bootstrap")

_EVT_CREATED = "users.bootstrap.created"
_EVT_UPDATED = "users.bootstrap.updated"
_EVT_NOOP = "users.bootstrap.noop"
_EVT_USER_NOOP = "users.bootstrap.user_noop"
_EVT_USER_CREATED = "users.bootstrap.user_created"
_EVT_FAILED = "users.bootstrap.failed"


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
    existing = (
        await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()

    # Look up by name first (works on both Postgres and SQLite regardless of UUID
    # storage format), then fall back to id-based lookup in case name was changed.
    admin_role = (
        await db.execute(select(Role).where(Role.name == ADMIN_ROLE_NAME))
    ).scalar_one_or_none()
    if admin_role is None:
        admin_role = (
            await db.execute(select(Role).where(Role.id == ADMIN_ROLE_ID))
        ).scalar_one_or_none()
    if admin_role is None:
        # The seed migration (e3ce9754e6dc) inserts this row, so in a real
        # deployment we should never hit this branch. Kept as a safety net for
        # tests (where `create_all` runs without data migrations) and for
        # scenarios where someone ran `alembic downgrade` past the seed
        # revision but not past the schema revision.
        admin_role = Role(
            id=ADMIN_ROLE_ID, name=ADMIN_ROLE_NAME, description=ADMIN_ROLE_DESCRIPTION
        )
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
        logger.info(_EVT_CREATED, extra={"email": email, "id": str(user.id)})
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
                    UserRole.user_id == existing.id, UserRole.role_id == admin_role.id
                )
            )
        ).scalar_one_or_none()
        if existing_link is None:
            db.add(UserRole(user_id=existing.id, role_id=admin_role.id))
        await db.commit()
        logger.info(_EVT_UPDATED, extra={"email": email, "id": str(existing.id)})
        return CreateAdminResult(user=existing, created=False)

    logger.info(_EVT_NOOP, extra={"email": email, "id": str(existing.id)})
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
    existing = (
        await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        logger.info(_EVT_USER_NOOP, extra={"email": email, "id": str(existing.id)})
        return CreateAdminResult(user=existing, created=False)

    user_role = (
        await db.execute(select(Role).where(Role.name == USER_ROLE_NAME))
    ).scalar_one_or_none()
    if user_role is None:
        user_role = (
            await db.execute(select(Role).where(Role.id == USER_ROLE_ID))
        ).scalar_one_or_none()
    if user_role is None:
        # Safety net — the seed migration normally inserts this row.
        user_role = Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description=USER_ROLE_DESCRIPTION)
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
    logger.info(_EVT_USER_CREATED, extra={"email": email, "id": str(user.id)})
    return CreateAdminResult(user=user, created=True)


async def _user_table_is_empty(db: AsyncSession) -> bool:
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return count == 0


def _read_dotenv_bootstrap_vars() -> dict[str, str]:
    """Return SM_USERS_BOOTSTRAP_* entries from ``.env`` (ignore everything else).

    ``UsersSettings`` deliberately doesn't use ``env_file`` — runtime fields
    come from the DB, and pulling the whole ``.env`` in would re-expose every
    SMTP/cookie/token secret as an env knob. So we re-read ``.env`` just for
    the four documented seed keys.
    """
    wanted = set(BOOTSTRAP_ENV_KEYS.values())
    return {k: v for k, v in parse_dotenv().items() if k in wanted}


def resolve_bootstrap_credentials(settings: UsersSettings) -> dict[str, str]:
    """Resolve the four bootstrap fields with the same precedence everywhere.

    Order: ``UsersSettings`` (test overrides) → ``os.environ`` (docker/systemd)
    → ``.env`` file (documented dev path). Used by both the boot-time admin
    seeder and the dev-only login-page quick-fill so the two stay in lockstep.
    """
    dotenv_vars = _read_dotenv_bootstrap_vars()
    return {
        attr: getattr(settings, attr) or os.environ.get(env_key) or dotenv_vars.get(env_key, "")
        for attr, env_key in BOOTSTRAP_ENV_KEYS.items()
    }


async def bootstrap_admin_from_env(app: FastAPI) -> None:
    """On-startup hook: create admin from env vars iff users table is empty.

    Resolves each of the four bootstrap fields via
    :func:`resolve_bootstrap_credentials`. If the admin email or password is
    still blank, returns silently — same if the users table already has rows
    (so restarts don't try to re-bootstrap).

    Optionally also creates a non-admin user from
    ``SM_USERS_BOOTSTRAP_USER_EMAIL`` + ``SM_USERS_BOOTSTRAP_USER_PASSWORD`` —
    useful in dev for testing non-admin flows alongside the admin account.
    """
    settings: UsersSettings = app.state.users.settings
    resolved = resolve_bootstrap_credentials(settings)
    email = resolved["bootstrap_email"]
    password = resolved["bootstrap_password"]
    user_email = resolved["bootstrap_user_email"]
    user_password = resolved["bootstrap_user_password"]

    if not email or not password:
        return

    session_factory = app.state.sm.db.session_factory
    async with session_factory() as session:
        if not await _user_table_is_empty(session):
            logger.debug("users.bootstrap.skipped (users table non-empty)")
            return

        try:
            await create_admin(session, email=email, password=password)
            if user_email and user_password:
                await create_standard_user(
                    session,
                    email=user_email,
                    password=user_password,
                )
        except Exception:
            logger.exception(_EVT_FAILED)
            raise
