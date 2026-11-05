"""Short-lived, app-local admin summaries, invalidated after user/role writes.

Only writes that can change a summary invalidate it: a user created, deleted,
enabled/disabled, verified or invited; a role created, deleted or renamed; a
membership added or removed. Logins, failed-login counters, password changes
and session revocations touch ``users_user`` too but change no figure here, so
they publish nothing. A qualifying transaction publishes at most once, after
commit. Without a cross-process transport (or if a message is lost) another
worker shows old totals until :data:`TTL_SECONDS` expires; these figures are
informational and never gate access.
"""

from __future__ import annotations

import time
from typing import Literal, overload

from simple_module_db.callbacks import register_on_commit
from sqlalchemy import event, func, inspect, select
from sqlalchemy.ext.asyncio import async_session
from sqlmodel import col

from users.admin.user_state import STATUS_CONDITIONS
from users.contracts.schemas import RoleListItem
from users.models import Role, User, UserRole

CHANNEL = "users.admin_summary"
TTL_SECONDS = 30.0
# Columns whose change can move a summary figure; ``None`` means any change.
_COUNTED: dict[str, frozenset[str] | None] = {
    User.__tablename__: frozenset({"is_active", "is_verified", "invited_at"}),
    Role.__tablename__: frozenset({"name", "description"}),
    UserRole.__tablename__: None,
}
_TOKEN = f"{CHANNEL}.publish"


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


def _cache(app) -> SummaryCache:
    """The app's cache, created on first use.

    Lazy so ``register_invalidations`` only subscribes: it must not assume an
    app it can write state onto (the hook is also called app-less).
    """
    cache = getattr(app.state, "users_admin_summary", None)
    if cache is None:
        cache = app.state.users_admin_summary = SummaryCache()
    return cache


def _changes_summary(obj, dirty: bool) -> bool:
    if not isinstance(obj, User | Role | UserRole):
        return False
    columns = _COUNTED[obj.__tablename__]
    if not dirty or columns is None:
        return True
    attrs = inspect(obj).attrs
    return any(attrs[name].history.has_changes() for name in columns)


def _statement_changes_summary(state) -> bool:
    if not (state.is_insert or state.is_update or state.is_delete):
        return False
    name = getattr(getattr(state.statement, "table", None), "name", None)
    if name not in _COUNTED:
        return False
    columns = _COUNTED[name]
    if not state.is_update or columns is None:
        return True
    values = getattr(state.statement, "_values", None)
    if not values:
        # Bulk-by-primary-key or ordered values: unknown columns, stay safe.
        return True
    return any(getattr(key, "key", key) in columns for key in values)


@overload
async def get_summary(app, db, *, roles: Literal[True]) -> list[RoleListItem]: ...


@overload
async def get_summary(app, db, *, roles: Literal[False]) -> dict[str, int]: ...


async def get_summary(app, db, *, roles):
    load = load_roles if roles else load_counts
    # Service-only callers and writes in progress need their transaction's own view.
    if app is None or db.new or db.dirty or db.deleted or db.info.get(CHANNEL):
        return await load(db)
    cache = _cache(app)
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
    from users.roles_cache import CHANNEL as ROLES_CHANNEL

    bus.subscribe(CHANNEL, lambda _: _cache(app).forget())
    bus.subscribe(ROLES_CHANNEL, lambda _: _cache(app).forget())


def register_writes(app):
    cache = _cache(app)
    if cache.wired:
        return
    cache.wired = True
    bus = app.state.sm.invalidation

    def written(session):
        session.info[CHANNEL] = True
        # One shared token per transaction: every qualifying flush queues a
        # callback (so a savepoint rollback cannot drop the only one), but the
        # first to run publishes and the rest are no-ops.
        token = session.info.setdefault(_TOKEN, {"sent": False})

        async def publish():
            if not token["sent"]:
                token["sent"] = True
                await bus.publish(CHANNEL)

        db = async_session(session)
        assert db is not None
        register_on_commit(db, publish)

    def before_flush(session, *_):
        if any(_changes_summary(obj, False) for obj in (*session.new, *session.deleted)) or any(
            _changes_summary(obj, True) for obj in session.dirty
        ):
            written(session)

    def before_execute(state):
        if _statement_changes_summary(state):
            written(state.session)

    def after_commit(session):
        if session.in_nested_transaction():
            return
        session.info.pop(_TOKEN, None)
        if session.info.pop(CHANNEL, False):
            # Also covers fastapi-users adapters that commit before request finalization.
            cache.forget()

    def after_rollback(session, transaction):
        if transaction.parent is None:
            session.info.pop(CHANNEL, None)
            session.info.pop(_TOKEN, None)

    session_class = app.state.sm.db.sync_session_class
    event.listen(session_class, "before_flush", before_flush)
    event.listen(session_class, "do_orm_execute", before_execute)
    event.listen(session_class, "after_commit", after_commit)
    event.listen(session_class, "after_soft_rollback", after_rollback)
