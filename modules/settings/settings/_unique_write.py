"""Race-safe inserts for the (scope, scope_id, key) unique key.

A read-then-insert cannot be made safe by reading harder: two requests can both
see "no row" and both insert. The unique constraint is the arbiter, so the
insert runs in a savepoint — a loser's ``IntegrityError`` rolls back only the
savepoint, leaving the request's transaction (and its session) usable.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from settings.models import Setting


class DuplicateSettingError(Exception):
    """A row with this (scope, scope_id, key) already exists."""


async def insert_if_free(db: AsyncSession, entity: Setting) -> bool:
    """Insert ``entity``; ``False`` when its (scope, scope_id, key) is already taken."""
    try:
        async with db.begin_nested():
            db.add(entity)
            await db.flush()
    except IntegrityError:
        return False
    return True
