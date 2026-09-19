"""Shared demo account — the one-click sign-in behind a public showcase instance.

Three pieces live here because they have to agree on one question ("is a demo
account configured, and who is it?"):

* :func:`resolve_demo_account` — reads the answer out of settings.
* :func:`ensure_demo_user` — reconciles the account row against that answer and
  caches its id on ``app.state.users``.
* :data:`SESSION_DEMO_KEY` — what a demo sign-in stamps on the session so the
  read-only guard can recognise it without a database read.

Deliberately *not* the dev quick-login buttons (``users.auth_local.views``):
those are development-only and paste real credentials into the form, which is
exactly what a published demo must not do. Here the password never leaves the
server — :mod:`users.auth_local.demo_api` mints the session directly.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi_users.password import PasswordHelper
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

logger = logging.getLogger("users.demo")

# Stamped on the session by the demo sign-in endpoint. The guard also matches
# on the user id, so this is not the only line of defence — it is what keeps
# the hot path off the database.
SESSION_DEMO_KEY = "is_demo"

_EVT_CREATED = "users.demo.created"
_EVT_RECONCILED = "users.demo.reconciled"
_EVT_DISABLED = "users.demo.disabled"

_ROLE_SEEDS = {
    ADMIN_ROLE_NAME: (ADMIN_ROLE_ID, ADMIN_ROLE_DESCRIPTION),
    USER_ROLE_NAME: (USER_ROLE_ID, USER_ROLE_DESCRIPTION),
}


@dataclass(frozen=True)
class DemoAccount:
    """The demo account an operator has asked for, normalised."""

    email: str
    password: str
    full_name: str
    role: str
    read_only: bool


def resolve_demo_account(settings: UsersSettings | None) -> DemoAccount | None:
    """The configured demo account, or ``None`` when the feature is off.

    A blank ``demo_email`` reads as off rather than as an error: the field is
    editable in the admin UI, and a half-finished edit should leave the sign-in
    page unchanged instead of failing the next boot.
    """
    if settings is None or not getattr(settings, "demo_mode", False):
        return None
    email = (settings.demo_email or "").strip()
    if not email:
        logger.warning("%s — demo_mode is on but demo_email is blank", _EVT_DISABLED)
        return None
    return DemoAccount(
        email=email,
        password=settings.demo_password or "",
        full_name=(settings.demo_full_name or "").strip() or "Demo User",
        role=settings.demo_role if settings.demo_role in _ROLE_SEEDS else USER_ROLE_NAME,
        read_only=bool(settings.demo_read_only),
    )


async def _role_row(db: AsyncSession, name: str) -> Role:
    """The Role row for ``name``, created from its seed constants if absent.

    Same shape as ``users.bootstrap``: the seed migration normally inserts
    both, so this only fires for tests built with ``create_all`` and for
    databases downgraded past the seed revision.
    """
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is not None:
        return role
    role_id, description = _ROLE_SEEDS[name]
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        role = Role(id=role_id, name=name, description=description)
        db.add(role)
        await db.flush()
    return role


async def _sync_role(db: AsyncSession, user: User, role_name: str) -> None:
    """Give the demo user exactly the configured role, dropping the other one.

    Dropping matters: flipping ``demo_role`` from ``admin`` back to ``user`` is
    how an operator revokes a demo that turned out to be too open, and a switch
    that only ever added rows would leave the admin grant in place.
    """
    wanted = await _role_row(db, role_name)
    links = (await db.execute(select(UserRole).where(UserRole.user_id == user.id))).scalars().all()
    managed = {rid for rid, _ in _ROLE_SEEDS.values()}
    if not any(link.role_id == wanted.id for link in links):
        db.add(UserRole(user_id=user.id, role_id=wanted.id))
    for link in links:
        if link.role_id != wanted.id and link.role_id in managed:
            await db.delete(link)


async def reconcile_demo_user(db: AsyncSession, account: DemoAccount) -> User:
    """Create or update the demo account row so it matches ``account``.

    Idempotent, and run on every boot *and* every settings reload — an operator
    who turns demo mode on in the admin UI of a long-running install must not
    have to restart to get the account.

    A configured ``demo_password`` is (re)applied every time, so changing it in
    the admin UI takes effect. A blank one is hashed from a fresh random secret
    on create only — that is what makes "reachable only via the button" true,
    and re-rolling it every boot would write an audit entry per worker per
    restart for a value nobody can use.
    """
    hasher = PasswordHelper()
    user = (
        await db.execute(select(User).where(func.lower(User.email) == account.email.lower()))
    ).scalar_one_or_none()
    created = user is None
    if user is None:
        user = User(email=account.email)
        db.add(user)

    if account.password:
        user.hashed_password = hasher.hash(account.password)
    elif created:
        user.hashed_password = hasher.hash(secrets.token_urlsafe(32))
    user.full_name = account.full_name
    user.is_active = True
    user.is_verified = True
    user.is_superuser = account.role == ADMIN_ROLE_NAME
    user.disabled_at = None
    await db.flush()
    await _sync_role(db, user, account.role)
    await db.commit()
    await db.refresh(user)
    logger.info(
        _EVT_CREATED if created else _EVT_RECONCILED,
        extra={"email": account.email, "id": str(user.id), "role": account.role},
    )
    return user


async def ensure_demo_user(app: FastAPI) -> uuid.UUID | None:
    """Reconcile the demo account and cache its id on ``app.state.users``.

    Returns the id (also stored as ``state.demo_user_id``) or ``None`` when no
    demo account is configured. Never raises: a demo instance failing to boot
    because the showcase account could not be written is a worse outcome than
    booting without the button.
    """
    state = app.state.users
    account = resolve_demo_account(state.settings)
    if account is None:
        state.demo_user_id = None
        return None
    try:
        async with app.state.sm.db.session_factory() as session:
            user = await reconcile_demo_user(session, account)
    except Exception:
        logger.exception("users.demo.failed", extra={"email": account.email})
        state.demo_user_id = None
        return None
    state.demo_user_id = user.id
    return user.id
