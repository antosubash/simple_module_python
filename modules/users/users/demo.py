"""Shared demo accounts — the one-click sign-ins behind a public showcase instance.

Three pieces live here because they have to agree on one question ("which demo
accounts are configured, and who are they?"):

* :func:`resolve_demo_accounts` — reads the answer out of settings.
* :func:`ensure_demo_users` — reconciles the rows against that answer and
  caches their ids on ``app.state.users``.
* :data:`SESSION_DEMO_KEY` — what a demo sign-in stamps on the session so the
  read-only guard can recognise it without a database read.

Two accounts, an administrator and an ordinary user, because the two halves of
the app look nothing alike: a visitor who only ever sees ``/admin/*`` never
meets the app an end user uses, and one who never sees it misses what the
framework is for. Each is independently switchable by blanking its email.

Deliberately *not* the dev quick-login buttons (``users.auth_local.views``):
those are development-only and paste real credentials into the form, which is
exactly what a published demo must not do. Here the passwords never leave the
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
# on the user ids, so this is not the only line of defence — it is what keeps
# the hot path off the database.
SESSION_DEMO_KEY = "is_demo"

_EVT_CREATED = "users.demo.created"
_EVT_RECONCILED = "users.demo.reconciled"
_EVT_DISABLED = "users.demo.disabled"

_ROLE_SEEDS = {
    ADMIN_ROLE_NAME: (ADMIN_ROLE_ID, ADMIN_ROLE_DESCRIPTION),
    USER_ROLE_NAME: (USER_ROLE_ID, USER_ROLE_DESCRIPTION),
}

# (role, email field, password field, seeded display name), in the order the
# buttons should appear on the sign-in card. Admin first: it is the surface
# someone evaluating the framework came to see.
_ACCOUNT_SPECS: tuple[tuple[str, str, str, str], ...] = (
    (ADMIN_ROLE_NAME, "demo_admin_email", "demo_admin_password", "Demo Administrator"),
    (USER_ROLE_NAME, "demo_user_email", "demo_user_password", "Demo User"),
)


@dataclass(frozen=True)
class DemoAccount:
    """One demo account an operator has asked for, normalised."""

    role: str
    email: str
    password: str
    full_name: str


def resolve_demo_accounts(settings: UsersSettings | None) -> tuple[DemoAccount, ...]:
    """The configured demo accounts, empty when the feature is off.

    A blank email reads as "don't offer this one" rather than as an error: the
    fields are editable in the admin UI, and a half-finished edit should leave
    the sign-in page with one button rather than failing the next boot. Blank
    both and ``demo_mode`` has nothing to turn on, which is worth a line in
    the log because the operator plainly meant something by switching it on.
    """
    if settings is None or not getattr(settings, "demo_mode", False):
        return ()
    accounts = tuple(
        DemoAccount(
            role=role,
            email=email,
            password=getattr(settings, password_field, "") or "",
            full_name=full_name,
        )
        for role, email_field, password_field, full_name in _ACCOUNT_SPECS
        if (email := (getattr(settings, email_field, "") or "").strip())
    )
    if not accounts:
        logger.warning("%s — demo_mode is on but no demo email is set", _EVT_DISABLED)
    return accounts


def resolve_demo_account(settings: UsersSettings | None, role: str) -> DemoAccount | None:
    """The configured demo account for ``role``, or ``None``."""
    return next((a for a in resolve_demo_accounts(settings) if a.role == role), None)


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

    Dropping matters: an operator who repoints ``demo_user_email`` at an
    address that previously served as the demo *admin* is demoting it, and a
    sync that only ever added rows would leave the admin grant in place.
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
    """Create or update one demo account's row so it matches ``account``.

    Idempotent, and run on every boot *and* every settings reload — an operator
    who turns demo mode on in the admin UI of a long-running install must not
    have to restart to get the accounts.

    A configured password is (re)applied every time, so changing it in the
    admin UI takes effect. A blank one is hashed from a fresh random secret on
    create only — that is what makes "reachable only through the button" true,
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


async def ensure_demo_users(app: FastAPI) -> tuple[uuid.UUID, ...]:
    """Reconcile every configured demo account; cache the ids on app state.

    Returns the ids (also stored as ``state.demo_user_ids``), empty when no
    demo account is configured. Never raises: a demo instance failing to boot
    because a showcase account could not be written is a worse outcome than
    booting without the buttons.

    One account failing does not cost the other — they are independent
    offers, and an admin demo that cannot be seeded is no reason to withdraw
    a working user demo.
    """
    state = app.state.users
    ids: list[uuid.UUID] = []
    for account in resolve_demo_accounts(state.settings):
        try:
            async with app.state.sm.db.session_factory() as session:
                user = await reconcile_demo_user(session, account)
        except Exception:
            logger.exception(
                "users.demo.failed", extra={"email": account.email, "role": account.role}
            )
            continue
        ids.append(user.id)
    state.demo_user_ids = tuple(ids)
    return state.demo_user_ids
