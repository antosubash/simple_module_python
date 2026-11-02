"""Durable cleanup of a deleted user's personal tokens."""

from simple_module_core.durable_events import DurableContext
from simple_module_core.user_events import UserDeleted
from simple_module_db.tenancy import all_tenants
from sqlmodel import col, delete

from api_tokens.constants import TokenKind
from api_tokens.models import ApiToken


async def purge_user_tokens(event: UserDeleted, ctx: DurableContext) -> None:
    with all_tenants():
        await ctx.db.execute(
            delete(ApiToken).where(
                col(ApiToken.kind) == TokenKind.PERSONAL,
                col(ApiToken.owner_user_id) == event.user_id,
            )
        )
