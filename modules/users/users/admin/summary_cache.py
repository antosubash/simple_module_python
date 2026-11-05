"""Short-lived, app-local admin summaries (state totals and role options).

This worker forgets its entries when a transaction that wrote a ``User``,
``Role`` or ``UserRole`` through the ORM commits. Other workers learn of a
change only through :func:`publish_after_commit`, which the admin service's
write paths call explicitly; other writes (logins, lockout counters, password
changes) publish nothing. Without a cross-process transport, or if a message
is lost, another worker shows old totals until :data:`TTL_SECONDS` expires;
these figures are informational and never gate access.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from simple_module_core.invalidation import InvalidationBus
from simple_module_db.callbacks import register_on_commit
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction
from sqlmodel import col

from users.admin.user_state import STATUS_CONDITIONS
from users.contracts.schemas import RoleListItem
from users.models import Role, User, UserRole

CHANNEL = "users.admin_summary"
TTL_SECONDS = 30.0
_COUNTS, _ROLES = "counts", "roles"


async def load_counts(db: AsyncSession) -> dict[str, int]:
    """One scan with ``COUNT(*) FILTER (WHERE …)`` per state rather than a
    round-trip each (Postgres and SQLite >= 3.30 both support it)."""
    keys = ("active", "unverified", "invited")
    stmt = select(*(func.count().filter(STATUS_CONDITIONS[k]()) for k in keys)).select_from(User)
    row = (await db.execute(stmt)).one()
    return {key: int(value) for key, value in zip(keys, row, strict=True)}


async def load_roles(db: AsyncSession) -> list[RoleListItem]:
    stmt = (
        select(
            Role.id,
            Role.name,
            Role.description,
            func.count(col(UserRole.user_id)).label("user_count"),
        )
        .outerjoin(UserRole, col(UserRole.role_id) == Role.id)
        .group_by(Role.id)
        .order_by(Role.name)
    )
    return [RoleListItem.model_construct(**row._mapping) for row in (await db.execute(stmt)).all()]


class SummaryCache:
    def __init__(self) -> None:
        self.slots: dict[str, tuple[Any, float]] = {}
        self.generation = 0
        self.wired = False

    def forget(self) -> None:
        self.slots.clear()
        self.generation += 1


def _cache(app: FastAPI) -> SummaryCache:
    """The app's cache, created on first use.

    Lazy so ``register_invalidations`` only subscribes: it must not assume an
    app it can write state onto (the hook is also called app-less).
    """
    cache = getattr(app.state, "users_admin_summary", None)
    if cache is None:
        cache = app.state.users_admin_summary = SummaryCache()
    return cache


async def _cached(
    app: FastAPI | None,
    db: AsyncSession,
    key: str,
    load: Callable[[AsyncSession], Awaitable[Any]],
) -> Any:
    # Service-only callers and writes in progress need their transaction's own view.
    if app is None or db.new or db.dirty or db.deleted or db.info.get(CHANNEL):
        return await load(db)
    cache = _cache(app)
    slot = cache.slots.get(key)
    now = time.monotonic()
    if slot is not None and now < slot[1]:
        return slot[0]
    generation = cache.generation
    # Never cache uncommitted rows or retain the request's transaction snapshot.
    async with app.state.sm.db.session_factory() as committed_db:
        value = await load(committed_db)
    if generation == cache.generation:
        cache.slots[key] = (value, now + TTL_SECONDS)
    return value


async def get_role_summary(app: FastAPI | None, db: AsyncSession) -> list[RoleListItem]:
    """Roles with their member counts, cached for :data:`TTL_SECONDS`."""
    value = await _cached(app, db, _ROLES, load_roles)
    return [item.model_copy() for item in value]


async def get_state_counts(app: FastAPI | None, db: AsyncSession) -> dict[str, int]:
    """Active/unverified/invited totals, cached for :data:`TTL_SECONDS`."""
    return dict(await _cached(app, db, _COUNTS, load_counts))


def publish_after_commit(app: FastAPI | None, db: AsyncSession) -> None:
    """Tell every worker to forget its summaries once ``db`` commits."""
    if app is None:
        return

    async def publish() -> None:
        await app.state.sm.invalidation.publish(CHANNEL)

    register_on_commit(db, publish)


def subscribe(bus: InvalidationBus, app: FastAPI) -> None:
    from users.roles_cache import CHANNEL as ROLES_CHANNEL

    bus.subscribe(CHANNEL, lambda _: _cache(app).forget())
    bus.subscribe(ROLES_CHANNEL, lambda _: _cache(app).forget())


def register_writes(app: FastAPI) -> None:
    """Forget this worker's summaries when a user/role write commits."""
    cache = _cache(app)
    if cache.wired:
        return
    cache.wired = True

    def before_flush(session: Session, *_: object) -> None:
        if any(
            isinstance(obj, User | Role | UserRole)
            for obj in (*session.new, *session.dirty, *session.deleted)
        ):
            session.info[CHANNEL] = True

    def after_commit(session: Session) -> None:
        # Also covers fastapi-users adapters that commit before request finalization.
        if not session.in_nested_transaction() and session.info.pop(CHANNEL, False):
            cache.forget()

    def after_rollback(session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is None:
            session.info.pop(CHANNEL, None)

    session_class = app.state.sm.db.sync_session_class
    event.listen(session_class, "before_flush", before_flush)
    event.listen(session_class, "after_commit", after_commit)
    event.listen(session_class, "after_soft_rollback", after_rollback)
