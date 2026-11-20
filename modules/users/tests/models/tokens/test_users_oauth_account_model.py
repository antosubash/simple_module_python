"""OAuth tokens must fit real IdP responses, including long Entra JWTs (#1054)."""

import pytest
import sqlalchemy as sa
from users.models import OAuthAccount, User


@pytest.mark.parametrize(("name", "nullable"), [("access_token", False), ("refresh_token", True)])
def test_oauth_token_columns_are_unbounded_text(name, nullable):
    column = sa.inspect(OAuthAccount).columns[name]
    assert isinstance(column.type, sa.Text)
    assert column.type.length is None
    assert column.nullable is nullable


@pytest.mark.parametrize("refresh_token", [None, "refresh" * 1024])
async def test_long_oauth_tokens_roundtrip(db_session, refresh_token):
    user = User(email="long-token@example.com")
    db_session.add(user)
    await db_session.flush()
    account = OAuthAccount(
        user_id=user.id,
        oauth_name="microsoft",
        account_id="entra-subject",
        account_email=user.email,
        access_token="access" * 1024,
        refresh_token=refresh_token,
    )
    db_session.add(account)
    await db_session.commit()
    account_id = account.id
    db_session.expunge_all()

    stored = await db_session.get(OAuthAccount, account_id)

    assert stored.access_token == "access" * 1024
    assert stored.refresh_token == refresh_token
