"""SQLAlchemyUserDatabase subclass that eager-loads roles."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from simple_module_db.deps import get_db
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.models import User, UserAccessToken


class UserDatabaseWithRoles(SQLAlchemyUserDatabase):
    """Always eager-load User.roles so fastapi-users can read role names
    without triggering implicit async lazy-loads."""

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
            .options(selectinload(self.user_table.roles))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


async def get_user_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[UserDatabaseWithRoles, None]:
    yield UserDatabaseWithRoles(session, User)


async def get_access_token_db(
    session: AsyncSession = Depends(get_db),
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase[UserAccessToken], None]:
    yield SQLAlchemyAccessTokenDatabase(session, UserAccessToken)
