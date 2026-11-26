"""A lost identity-link race has the normal OAuth refusal, not a 500 (#1153)."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from users.accounts.db_adapter import UserDatabaseWithRoles
from users.models import OAuthAccount, User
from users.oauth.errors import OAuthAccountLinkedElsewhereError


@pytest.mark.parametrize("same_user", [False, True])
async def test_duplicate_identity_insert_maps_to_link_refusal(db_session, same_user):
    first = User(email="first@example.com")
    second = first if same_user else User(email="second@example.com")
    db_session.add_all([first, second])
    await db_session.commit()
    db = UserDatabaseWithRoles(db_session, User, OAuthAccount)
    link = {
        "oauth_name": "github",
        "account_id": "subject",
        "account_email": "first@example.com",
        "access_token": "token",
    }
    await db.add_oauth_account(first, link)

    # The other callback's identity lookup preceded the winning insert. Calling
    # the adapter directly exercises the actual unique violation on its insert.
    with pytest.raises(OAuthAccountLinkedElsewhereError):
        await db.add_oauth_account(second, link)

    # The adapter must leave the session usable after the failed insert.
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(OAuthAccount)) == 1


async def test_unrelated_integrity_error_is_not_an_identity_refusal(db_session):
    user = User(email="user@example.com")
    db_session.add(user)
    await db_session.commit()
    db = UserDatabaseWithRoles(db_session, User, OAuthAccount)
    with pytest.raises(IntegrityError):
        await db.add_oauth_account(
            user,
            {
                "oauth_name": "github",
                "account_id": "subject",
                "account_email": user.email,
                "access_token": None,
            },
        )
