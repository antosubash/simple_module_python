"""SQLAlchemyUserDatabase subclass that eager-loads roles."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from simple_module_db.deps import get_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.models import OAuthAccount, User, UserAccessToken


class UserDatabaseWithRoles(SQLAlchemyUserDatabase):
    """Eager-load User.roles so fastapi-users can read role names without
    triggering implicit async lazy-loads.

    ``oauth_accounts`` is ``lazy="noload"`` on the model, so it is *not* loaded
    on the read-only auth path (``get`` backs ``current_user`` on every
    request). It is eager-loaded only in ``get_by_email`` — the entry point for
    fastapi-users' OAuth association flow, which appends to the collection and
    therefore needs it materialised. ``get_by_oauth_account`` (base class) runs
    its own join and does not depend on the relationship being loaded.
    """

    async def get(self, id):
        stmt = (
            select(self.user_table)
            .where(self.user_table.id == id)
            .options(selectinload(self.user_table.roles))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email):
        stmt = (
            select(self.user_table)
            .where(func.lower(self.user_table.email) == email.lower())
            .options(
                selectinload(self.user_table.roles),
                selectinload(self.user_table.oauth_accounts),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


async def get_user_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[UserDatabaseWithRoles, None]:
    # OAuthAccount enables fastapi-users' OAuth router (get_by_oauth_account /
    # add_oauth_account / update_oauth_account). Password-only flows are
    # unaffected — those code paths never touch oauth_account_table.
    yield UserDatabaseWithRoles(session, User, OAuthAccount)


async def get_access_token_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase[UserAccessToken], None]:
    yield SQLAlchemyAccessTokenDatabase(session, UserAccessToken)
