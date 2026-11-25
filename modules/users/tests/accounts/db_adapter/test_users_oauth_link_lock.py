"""The OAuth link guard holds across connections (#1128).

The callback tests drive one app, where an in-memory SQLite engine shares a
single connection. Two workers share neither, so the adapter's write lock is
what stops two different identities of one provider linking to the same
account. Exercised here on two real connections to a file database.
"""

from __future__ import annotations

import uuid

import pytest
from simple_module_db import init_db
from sqlalchemy.exc import OperationalError
from users.accounts.db_adapter import UserDatabaseWithRoles, _begin_sqlite_link_transaction
from users.models import OAuthAccount, User
from users.oauth.errors import OAuthAccountLinkedElsewhereError

pytestmark = pytest.mark.anyio

_PROVIDER = "microsoft"


def _link(account_id: str) -> dict[str, str]:
    return {
        "oauth_name": _PROVIDER,
        "account_id": account_id,
        "account_email": "jane@corp.com",
        "access_token": "token",
    }


async def test_second_identity_waits_for_the_first_link_then_is_refused(tmp_path) -> None:
    state = init_db(f"sqlite+aiosqlite:///{tmp_path / 'link.db'}", sqlite_busy_timeout_ms=100)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(User.metadata.create_all)
        user_id = uuid.uuid4()
        async with state.session_factory() as seed:
            seed.add(User(id=user_id, email="jane@corp.com", hashed_password="x"))
            await seed.commit()

        async with state.session_factory() as first, state.session_factory() as second:
            # The first callback holds the link lock between its check and insert.
            connection = await first.connection()
            await connection.run_sync(_begin_sqlite_link_transaction)

            second_db = UserDatabaseWithRoles(second, User, OAuthAccount)
            with pytest.raises(OperationalError, match="locked"):
                await second_db.add_oauth_account(await second.get(User, user_id), _link("oid-2"))
            await second.rollback()

            first_db = UserDatabaseWithRoles(first, User, OAuthAccount)
            await first_db.add_oauth_account(await first.get(User, user_id), _link("oid-1"))

            # Released at commit: the waiting callback re-checks and is refused.
            with pytest.raises(OAuthAccountLinkedElsewhereError):
                await second_db.add_oauth_account(await second.get(User, user_id), _link("oid-2"))
            await second.rollback()

        async with state.session_factory() as check:
            links = (await check.execute(OAuthAccount.__table__.select())).all()
            assert [(row.oauth_name, row.account_id) for row in links] == [(_PROVIDER, "oid-1")]
    finally:
        await state.engine.dispose()
