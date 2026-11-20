"""OAuth tokens must fit real IdP responses, including long Entra JWTs (#1054)."""

import pytest
import sqlalchemy as sa
from sqlmodel import Session
from users.models import OAuthAccount, User


@pytest.mark.parametrize(("name", "nullable"), [("access_token", False), ("refresh_token", True)])
def test_oauth_token_columns_are_unbounded_text(name, nullable):
    column = sa.inspect(OAuthAccount).columns[name]
    assert isinstance(column.type, sa.Text)
    assert column.type.length is None
    assert column.nullable is nullable


@pytest.mark.parametrize("refresh_token", [None, "refresh" * 1024])
def test_long_oauth_tokens_roundtrip(refresh_token):
    engine = sa.create_engine("sqlite://")
    User.metadata.create_all(engine)
    user = User(email="long-token@example.com")
    try:
        with Session(engine) as session:
            session.add(user)
            session.flush()
            account = OAuthAccount(
                user_id=user.id,
                oauth_name="microsoft",
                account_id="entra-subject",
                account_email=user.email,
                access_token="access" * 1024,
                refresh_token=refresh_token,
            )
            session.add(account)
            session.commit()
            account_id = account.id
            session.expunge_all()

            stored = session.get(OAuthAccount, account_id)

            assert stored.access_token == "access" * 1024
            assert stored.refresh_token == refresh_token
    finally:
        engine.dispose()
