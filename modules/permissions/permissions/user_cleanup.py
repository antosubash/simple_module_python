"""Revoke a deleted user's direct permission grants."""

from simple_module_core.durable_events import DurableContext
from simple_module_core.invalidation import Invalidation
from simple_module_db.callbacks import register_on_commit
from sqlmodel import col, delete
from users.contracts.events import UserDeleted

from permissions.grants import CHANNEL, apply_invalidation
from permissions.models import UserPermission


async def purge_user_grants(event: UserDeleted, ctx: DurableContext) -> None:
    await ctx.db.execute(delete(UserPermission).where(col(UserPermission.user_id) == event.user_id))
    register_on_commit(
        ctx.db, lambda: apply_invalidation(Invalidation(channel=CHANNEL, key=str(event.user_id)))
    )
