"""SQLAlchemyUserDatabase subclass that eager-loads roles."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from simple_module_db.engine.callbacks import run_on_commit_callbacks
from simple_module_db.engine.deps import get_db
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from users.accounts.token_storage import prune_tokens
from users.core.settings import DEFAULT_REFRESH_TOKEN_FAMILY_MAX_AGE_DAYS
from users.models import OAuthAccount, User, UserAccessToken
from users.oauth.errors import OAuthAccountLinkedElsewhereError


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

    async def create(self, create_dict):
        create_dict = {**create_dict, "email": create_dict["email"].lower()}
        user = self.user_table(**create_dict)
        # A savepoint scopes a lost email race to this insert: rolling back the
        # whole request session would also drop on-commit work queued for other
        # accounts in the same request (bulk invites). Commit and refresh as the
        # upstream adapter does.
        try:
            async with self.session.begin_nested():
                self.session.add(user)
        except IntegrityError:
            # Only translate an email race; unrelated constraint errors still surface.
            if await self.get_by_email(create_dict["email"]) is not None:
                raise UserAlreadyExists() from None
            raise
        await self.session.commit()
        await run_on_commit_callbacks(self.session)
        await self.session.refresh(user)
        return user

    async def update(self, user, update_dict):
        user = await super().update(user, update_dict)
        await run_on_commit_callbacks(self.session)
        return user

    async def delete(self, user):
        await super().delete(user)
        await run_on_commit_callbacks(self.session)

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

    async def add_oauth_account(self, user, create_dict):
        # Serialize link additions for this user until the upstream insert
        # commits. SQLite has no row locks and can defer BEGIN until the write.
        connection = await self.session.connection()
        if connection.dialect.name == "sqlite":
            await connection.run_sync(_begin_sqlite_link_transaction)
        else:
            await self.session.execute(select(User.id).where(User.id == user.id).with_for_update())
        # Query fresh links under the lock, independent of the ORM collection
        # loaded during the earlier email lookup.
        conflict = select(OAuthAccount.id).where(
            OAuthAccount.user_id == user.id,
            OAuthAccount.oauth_name == create_dict["oauth_name"],
            OAuthAccount.account_id != create_dict["account_id"],
        )
        if await self.session.scalar(conflict.limit(1)) is not None:
            raise OAuthAccountLinkedElsewhereError
        try:
            return await super().add_oauth_account(user, create_dict)
        except IntegrityError as exc:
            # The upstream adapter commits; recover the failed transaction even
            # when an unrelated constraint error must propagate.
            await self.session.rollback()
            if _is_oauth_identity_conflict(exc):
                raise OAuthAccountLinkedElsewhereError from None
            raise


def _is_oauth_identity_conflict(exc: IntegrityError) -> bool:
    original = exc.orig
    if getattr(original, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
        return str(original) == (
            "UNIQUE constraint failed: users_oauth_account.oauth_name, "
            "users_oauth_account.account_id"
        )
    # psycopg exposes diag; SQLAlchemy's asyncpg adapter chains the driver error.
    diagnostic = getattr(original, "diag", None) or getattr(original, "__cause__", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return sqlstate == "23505" and (
        getattr(diagnostic, "constraint_name", None) == "uq_users_oauth_account_identity"
    )


def _begin_sqlite_link_transaction(connection):
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


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
