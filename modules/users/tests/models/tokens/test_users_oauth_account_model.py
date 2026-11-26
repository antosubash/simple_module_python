"""OAuth tokens must fit real IdP responses, including long Entra JWTs (#1054)."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from users.models import OAuthAccount, User


def test_model_rejects_duplicate_provider_identity():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            User.metadata.create_all(conn)
            users = [User(email="first@example.com"), User(email="second@example.com")]
            for user in users:
                conn.execute(User.__table__.insert().values(id=user.id, email=user.email))
            link = {
                "oauth_name": "github",
                "account_id": "subject",
                "account_email": "provider@example.com",
                "access_token": "token",
            }
            conn.execute(OAuthAccount.__table__.insert().values(user_id=users[0].id, **link))
            with pytest.raises(IntegrityError):
                conn.execute(OAuthAccount.__table__.insert().values(user_id=users[1].id, **link))
            link["oauth_name"] = "microsoft"
            conn.execute(OAuthAccount.__table__.insert().values(user_id=users[1].id, **link))
    finally:
        engine.dispose()


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
