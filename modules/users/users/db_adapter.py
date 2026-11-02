"""SQLAlchemyUserDatabase subclass that eager-loads roles."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from simple_module_db.deps import get_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from users.models import OAuthAccount, User, UserAccessToken
from users.settings import DEFAULT_REFRESH_TOKEN_FAMILY_MAX_AGE_DAYS
from users.token_storage import prune_tokens


class UserDatabaseWithRoles(SQLAlchemyUserDatabase):
    """Eager-load User.roles so fastapi-users can read role names without
    triggering implicit async lazy-loads.

    ``oauth_accounts`` is ``lazy="selectin"`` on the model (needed for the ORM
    delete-orphan cascade, since SQLite doesn't enforce the FK). ``get`` backs
    ``current_user`` on every request and never reads OAuth accounts, so it
    suppresses that load with ``noload``. ``get_by_email`` — the entry point for
    fastapi-users' OAuth association flow, which appends to the collection —
    lets the model's default ``selectin`` materialise it.
    """

    async def get(self, id):
        stmt = (
            select(self.user_table)
            .where(self.user_table.id == id)
            .options(
                selectinload(self.user_table.roles),
                noload(self.user_table.oauth_accounts),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email):
        stmt = (
            select(self.user_table)
            .where(func.lower(self.user_table.email) == email.lower())
            .options(
                selectinload(self.user_table.roles),
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


class PruningAccessTokenDatabase(SQLAlchemyAccessTokenDatabase[UserAccessToken]):
    """Clean up spent credentials when a cookie login mints an access token."""

    def __init__(
        self,
        session,
        access_token_table,
        *,
        family_max_age_days: int = DEFAULT_REFRESH_TOKEN_FAMILY_MAX_AGE_DAYS,
    ):
        super().__init__(session, access_token_table)
        self.family_max_age_days = family_max_age_days

    async def create(self, create_dict):
        await prune_tokens(
            self.session,
            create_dict["user_id"],
            datetime.now(UTC),
            family_max_age_days=self.family_max_age_days,
        )
        return await super().create(create_dict)


async def get_access_token_db(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase[UserAccessToken], None]:
    yield PruningAccessTokenDatabase(
        session,
        UserAccessToken,
        family_max_age_days=request.app.state.users.settings.refresh_token_family_max_age_days,
    )
