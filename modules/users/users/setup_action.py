"""The wizard action that completes ``users.administrator``: create the first admin.

Anonymous by necessity — it runs before any account exists — so the bounds on
it are the whole of its security:

1. The wizard calls it only while *this* step is pending (no active
   superuser), never merely while "setup mode" is on. A live install whose
   schema falls behind head re-enters setup mode with its administrators
   intact; gated on the weaker condition this would mint a superuser there.
2. That check runs before the handler, outside any transaction, so two
   concurrent requests can both pass it. The handler therefore takes a
   database-level lock and re-checks **inside the transaction that inserts**:
   the loser of the race sees the winner's committed admin and is refused.
3. The password goes through the users module's real policy
   (``UserManager.validate_password``). ``create_admin`` writes the hash
   directly and never consults it, and a local copy of "at least 8
   characters" is exactly how it once drifted from the policy.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi_users import exceptions as fu_exceptions
from pydantic import EmailStr
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from users.bootstrap import create_admin
from users.manager import UserManager
from users.models import User

logger = logging.getLogger(__name__)

# Arbitrary, fixed 64-bit key for pg_advisory_xact_lock. Only this action
# takes it, so any constant that no other module uses will do.
_PG_LOCK_KEY = 0x534D_5345_5455_5041  # "SMSETUPA"


class AdministratorIn(SQLModel):
    email: EmailStr
    password: str
    full_name: str | None = None


async def _validate_password(password: str, email: str) -> None:
    try:
        await UserManager.validate_password(UserManager, password, SimpleNamespace(email=email))
    except fu_exceptions.InvalidPasswordException as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc


async def _lock_admin_creation(session: AsyncSession) -> None:
    """Serialize admin creation across workers for the rest of this transaction.

    * Postgres: a transaction-scoped advisory lock, released at commit or
      rollback. Taken before the re-check, so under READ COMMITTED the re-check
      reads every admin committed by whoever held the lock before us.
    * SQLite: a write statement that matches no rows. It still opens a write
      transaction and takes the database's RESERVED lock, which a second
      writer blocks on (``busy_timeout``) until this one commits; its own
      re-check then runs against the committed admin.
    """
    connection = await session.connection()
    if connection.dialect.name == "postgresql":
        await session.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _PG_LOCK_KEY})
        return
    table = User.__table__
    await session.execute(
        sa.update(table).where(sa.false()).values(is_superuser=table.c.is_superuser)
    )


async def _has_active_superuser(session: AsyncSession) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.is_superuser.is_(True), User.is_active.is_(True))
    )
    return bool(count)


def _process_lock(app) -> asyncio.Lock:
    """One in-process lock per app.

    The database lock is the real guarantee; this one keeps concurrent
    requests in one worker from contending on it at all — and is what
    serializes them on an in-memory SQLite engine, whose sessions share a
    single connection and so cannot lock each other out.
    """
    lock = getattr(app.state, "users_setup_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.users_setup_lock = lock
    return lock


async def create_first_administrator(request: Request, data: dict) -> dict:
    """Create the install's first administrator — the ``users.administrator`` action."""
    try:
        payload = AdministratorIn.model_validate(data)
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=422, detail="; ".join(e["msg"] for e in exc.errors())
        ) from exc
    await _validate_password(payload.password, payload.email)

    async with _process_lock(request.app), request.app.state.sm.db.session_factory() as session:
        await _lock_admin_creation(session)
        if await _has_active_superuser(session):
            await session.rollback()
            raise HTTPException(status_code=409, detail="An administrator already exists.")
        # create_admin commits, which is what releases the database lock —
        # after the user row and its admin role are both written.
        result = await create_admin(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        )
        if not result.created:
            # The address belongs to an account that is not an active
            # superuser. create_admin(force=False) leaves it untouched, so
            # nothing was granted — say so rather than reporting success
            # for a step that is still pending.
            await session.rollback()
            raise HTTPException(
                status_code=409, detail="An account with this email already exists."
            )

    logger.info("Setup: administrator created (%s)", payload.email)
    return {"created": True, "email": payload.email}
