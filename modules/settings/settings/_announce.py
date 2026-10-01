"""Publish a per-(tenant, key) invalidation after a settings write commits.

Kept out of ``service.py`` (and its 300-line budget). See
``settings.contracts.invalidation`` for the key format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_db.callbacks import register_on_commit

from settings.constants import INVALIDATION_CHANNEL, SCOPE_SYSTEM, SCOPE_TENANT
from settings.contracts.invalidation import invalidation_key

if TYPE_CHECKING:
    from simple_module_core.invalidation import InvalidationBus
    from sqlalchemy.ext.asyncio import AsyncSession


def announce(
    db: AsyncSession, bus: InvalidationBus | None, scope: str, scope_id: str, key: str
) -> None:
    """Queue the notice for this session's commit; user-scope writes have no consumer.

    After commit, not inline: a consumer that drops its entry before the row is
    durable re-reads the *old* value and caches it for a full TTL.
    """
    if bus is None or scope not in (SCOPE_SYSTEM, SCOPE_TENANT):
        return
    wire_key = invalidation_key(scope_id if scope == SCOPE_TENANT else None, key)

    async def publish() -> None:
        await bus.publish(INVALIDATION_CHANNEL, key=wire_key)

    register_on_commit(db, publish)
