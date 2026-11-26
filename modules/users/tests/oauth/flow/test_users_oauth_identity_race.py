"""A duplicate-identity race must reach the normal browser/API refusal (#1153)."""

import pytest
import sqlalchemy as sa
from _users_oauth_support import install_fake_provider, oauth_callback, seed_password_user
from sqlalchemy.exc import IntegrityError
from users.accounts.db_adapter import UserDatabaseWithRoles
from users.models import OAuthAccount


@pytest.mark.parametrize("browser", [False, True])
async def test_lost_identity_race_refuses_login(users_app, anon_client, monkeypatch, browser):
    target = await seed_password_user(users_app, "target@example.com", is_verified=True)
    winner = await seed_password_user(users_app, "winner@example.com", is_verified=True)
    install_fake_provider(users_app, "shared-subject", "target@example.com")
    original = UserDatabaseWithRoles.add_oauth_account

    async def winner_links_before_insert(self, user, create_dict):
        # Both callback lookups missed the winner. Commit the competing link
        # immediately before the real adapter insert to force a unique violation.
        self.session.add(OAuthAccount(user_id=winner, **create_dict))
        await self.session.commit()
        return await original(self, user, create_dict)

    monkeypatch.setattr(UserDatabaseWithRoles, "add_oauth_account", winner_links_before_insert)
    anon_client.headers["accept"] = "text/html" if browser else "application/json"

    response = await oauth_callback(anon_client)

    if browser:
        assert response.status_code == 303
        assert response.headers["location"] == "/users/login?oauth_error=account_linked_elsewhere"
    else:
        assert response.status_code == 403
        assert response.json()["detail"] == "OAUTH_ACCOUNT_LINKED_ELSEWHERE"
    assert users_app.state.users.settings.cookie_name not in response.cookies
    async with users_app.state.sm.db.session_factory() as db:
        links = (await db.execute(sa.select(OAuthAccount))).scalars().all()
        assert [(link.user_id, link.account_id) for link in links] == [(winner, "shared-subject")]
        assert all(link.user_id != target for link in links)


async def test_identity_race_does_not_hide_unrelated_integrity_error(
    users_app, anon_client, monkeypatch
):
    await seed_password_user(users_app, "target@example.com", is_verified=True)
    winner = await seed_password_user(users_app, "winner@example.com", is_verified=True)
    install_fake_provider(users_app, "shared-subject", "target@example.com")
    original = UserDatabaseWithRoles.add_oauth_account

    async def invalid_insert_after_winner(self, user, create_dict):
        self.session.add(OAuthAccount(user_id=winner, **create_dict))
        await self.session.commit()
        # NOT NULL fails before uniqueness. The identity's existence must not
        # turn this unrelated failure into an ordinary authentication refusal.
        return await original(self, user, {**create_dict, "access_token": None})

    monkeypatch.setattr(UserDatabaseWithRoles, "add_oauth_account", invalid_insert_after_winner)
    with pytest.raises(IntegrityError):
        await oauth_callback(anon_client)


@pytest.mark.parametrize(
    ("violation", "constraint", "expected"),
    [
        ("UniqueViolationError", "uq_users_oauth_account_identity", True),
        ("UniqueViolationError", "uq_users_user_email", False),
        ("CheckViolationError", "uq_users_oauth_account_identity", False),
    ],
)
def test_postgres_race_classification(violation, constraint, expected):
    from types import SimpleNamespace

    import asyncpg
    from sqlalchemy.dialects.postgresql.asyncpg import (
        AsyncAdapt_asyncpg_connection,
        AsyncAdapt_asyncpg_dbapi,
    )
    from users.accounts.db_adapter import _is_oauth_identity_conflict

    # Exercise SQLAlchemy's actual asyncpg exception translation without a server.
    original = getattr(asyncpg, violation)("constraint violation")
    original.constraint_name = constraint
    dbapi = AsyncAdapt_asyncpg_dbapi(asyncpg)
    connection = SimpleNamespace(_connection=SimpleNamespace(is_closed=lambda: False), dbapi=dbapi)
    with pytest.raises(dbapi.IntegrityError) as caught:
        AsyncAdapt_asyncpg_connection._handle_exception(connection, original)
    assert _is_oauth_identity_conflict(IntegrityError(None, None, caught.value)) is expected
