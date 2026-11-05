"""Short-lived, app-local admin summaries, invalidated after user/role writes."""

from __future__ import annotations

import time
from typing import Literal, overload

from simple_module_db.callbacks import register_on_commit
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_session
from sqlmodel import col

from users.admin.user_state import STATUS_CONDITIONS
from users.contracts.schemas import RoleListItem
from users.models import Role, User, UserRole

CHANNEL = "users.admin_summary"
TTL_SECONDS = 30.0
_TABLES = {User.__tablename__, Role.__tablename__, UserRole.__tablename__}


async def load_counts(db) -> dict[str, int]:
    keys = ("active", "unverified", "invited")
    stmt = select(*(func.count().filter(STATUS_CONDITIONS[k]()) for k in keys)).select_from(User)
    row = (await db.execute(stmt)).one()
    return {key: int(value) for key, value in zip(keys, row, strict=True)}


async def load_roles(db) -> list[RoleListItem]:
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
    def __init__(self):
        self.slots = {}
        self.generation = 0
        self.wired = False

    def forget(self):
        self.slots.clear()
        self.generation += 1


@overload
async def get_summary(app, db, *, roles: Literal[True]) -> list[RoleListItem]: ...


@overload
async def get_summary(app, db, *, roles: Literal[False]) -> dict[str, int]: ...


async def get_summary(app, db, *, roles):
    load = load_roles if roles else load_counts
    # Service-only callers and writes in progress need their transaction's own view.
    if app is None or db.new or db.dirty or db.deleted or db.info.get(CHANNEL):
        return await load(db)
    cache = app.state.users_admin_summary
    slot = cache.slots.get(roles)
    now = time.monotonic()
    if slot is None or now >= slot[1]:
        generation = cache.generation
        # Never cache uncommitted rows or retain the request's transaction snapshot.
        async with app.state.sm.db.session_factory() as committed_db:
            value = await load(committed_db)
        if generation == cache.generation:
            cache.slots[roles] = (value, now + TTL_SECONDS)
    else:
        value = slot[0]
    return [item.model_copy() for item in value] if roles else dict(value)


def subscribe(bus, app):
    cache = SummaryCache()
    app.state.users_admin_summary = cache
    bus.subscribe(CHANNEL, lambda _: cache.forget())
    from users.roles_cache import CHANNEL as ROLES_CHANNEL

    bus.subscribe(ROLES_CHANNEL, lambda _: cache.forget())


def register_writes(app):
    cache = app.state.users_admin_summary
    if cache.wired:
        return
    cache.wired = True
    bus = app.state.sm.invalidation

    def written(session):
        session.info[CHANNEL] = True
        db = async_session(session)
        assert db is not None
        register_on_commit(db, lambda: bus.publish(CHANNEL))

    def before_flush(session, *_):
        if any(
            isinstance(obj, User | Role | UserRole)
            for obj in (*session.new, *session.dirty, *session.deleted)
        ):
            written(session)

    def before_execute(state):
        if (state.is_insert or state.is_update or state.is_delete) and (
            getattr(getattr(state.statement, "table", None), "name", None) in _TABLES
        ):
            written(state.session)

    def after_commit(session):
        if not session.in_nested_transaction() and session.info.pop(CHANNEL, False):
            # Also covers fastapi-users adapters that commit before request finalization.
            cache.forget()

    def after_rollback(session, transaction):
        if transaction.parent is None:
            session.info.pop(CHANNEL, None)

    session_class = app.state.sm.db.sync_session_class
    event.listen(session_class, "before_flush", before_flush)
    event.listen(session_class, "do_orm_execute", before_execute)
    event.listen(session_class, "after_commit", after_commit)
    event.listen(session_class, "after_soft_rollback", after_rollback)
