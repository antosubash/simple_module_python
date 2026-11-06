"""Owner-safe demotion and removal: the "at least one owner" rule, atomically.

Counting owners and then writing is a check-then-act race: two owners
demoting each other at once both see two owners and both succeed, leaving a
tenant nobody can ever administer again. So the rule lives in the write
itself — the UPDATE/DELETE only matches while *another* owner exists, and
zero affected rows means "this was the last owner".

On SQLite writers serialise and the condition is evaluated at write time,
which settles it. On Postgres (READ COMMITTED) two writes to different rows
would not block each other, so callers also hold the tenant row lock
(``TenantService.lock``) — the second request waits for the first to commit
and then evaluates the condition against it.
"""

from __future__ import annotations

from simple_module_db import mark_written
from sqlalchemy import delete, exists, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from tenants.core.constants import MembershipRole
from tenants.models import Membership


def _another_owner(membership: Membership):
    other = aliased(Membership)
    return exists().where(
        col(other.tenant_id) == membership.tenant_id,
        col(other.role) == MembershipRole.OWNER,
        col(other.id) != membership.id,
    )


async def demote_owner(db: AsyncSession, membership: Membership, role: str) -> bool:
    """Set ``role`` on an owner's membership unless they are the last owner."""
    stmt = (
        update(Membership)
        .where(col(Membership.id) == membership.id, _another_owner(membership))
        .values(role=role)
        .execution_options(synchronize_session=False)
    )
    applied = (await db.execute(stmt)).rowcount == 1
    if applied:
        _mark_written(db)
        await db.refresh(membership)
    return applied


async def remove_owner(db: AsyncSession, membership: Membership) -> bool:
    """Delete an owner's membership unless they are the last owner."""
    stmt = (
        delete(Membership)
        .where(col(Membership.id) == membership.id, _another_owner(membership))
        .execution_options(synchronize_session=False)
    )
    applied = (await db.execute(stmt)).rowcount == 1
    if applied:
        _mark_written(db)
        db.expunge(membership)
    return applied


def _mark_written(db: AsyncSession) -> None:
    # Goes through ``mark_written`` so the stamp follows savepoint rollbacks; a
    # bare ``info[SESSION_HAS_WRITES_KEY] = True`` is dropped by an unrelated
    # savepoint rollback (#809).
    mark_written(db)
