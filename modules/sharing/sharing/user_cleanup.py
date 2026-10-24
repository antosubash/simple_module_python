"""Revoke shares addressed to a deleted principal across tenants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_module_core.durable_events import DurableContext
from simple_module_db import all_tenants
from sqlmodel import col, delete

from sharing.constants import SUBJECT_USER
from sharing.models import ResourceShare

if TYPE_CHECKING:
    from users.contracts.events import UserDeleted


async def purge_user_shares(event: UserDeleted, ctx: DurableContext) -> None:
    with all_tenants():
        await ctx.db.execute(
            delete(ResourceShare).where(
                col(ResourceShare.subject_type) == SUBJECT_USER,
                col(ResourceShare.subject_id) == str(event.user_id),
            )
        )
