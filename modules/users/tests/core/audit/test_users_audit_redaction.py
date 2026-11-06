"""User credentials and token identities are redacted from audit capture."""

import uuid
from datetime import UTC, datetime

import pytest
from simple_module_db import record_bulk_audit
from simple_module_db.audit import collect_audit_records
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session
from users.models import OAuthAccount, RefreshToken, User, UserAccessToken

TOKENS = [UserAccessToken, RefreshToken]


@pytest.fixture
def credential_session():
    engine = create_engine("sqlite://")
    records = []
    bind_engine_policy(
        engine,
        EngineTenancy(
            tenant_strict=False, audit_callback=lambda session, batch: records.extend(batch)
        ),
    )

    class AuditSession(Session):
        pass

    attach_session_listeners(AuditSession)
    try:
        User.metadata.create_all(engine)
        with AuditSession(engine) as session:
            yield session, records
    finally:
        engine.dispose()


def _created(entity):
    with Session() as session:
        session.add(entity)
        return collect_audit_records(session)[0]


def test_user_and_oauth_credentials_are_redacted():
    user = {
        c["field"]: c["new"] for c in _created(User(email="a@test", hashed_password="x")).changes
    }
    assert user["hashed_password"] == "[redacted]"
    oauth = OAuthAccount(
        user_id=uuid.uuid4(),
        access_token="x",
        refresh_token="x",
        oauth_name="test",
        account_id="1",
        account_email="a@test",
    )
    changes = {c["field"]: c["new"] for c in _created(oauth).changes}
    assert changes["access_token"] == changes["refresh_token"] == "[redacted]"


@pytest.mark.parametrize("cls", TOKENS)
def test_token_primary_key_is_redacted(cls):
    token = cls(token="private", user_id=uuid.uuid4(), expires_at=datetime.now(UTC))
    assert _created(token).entity_id == "[redacted]"


def test_password_update_redacts_both_sides(credential_session):
    session, records = credential_session
    user = User(email="update@test", hashed_password="old-private")
    session.add(user)
    session.flush()
    records.clear()
    user.hashed_password = "new-private"
    session.flush()
    assert records[0].changes == [
        {"field": "hashed_password", "old": "[redacted]", "new": "[redacted]"}
    ]


def test_bulk_password_update_redacted(credential_session):
    session, records = credential_session
    session.add(User(email="bulk@test", hashed_password="old-private"))
    session.flush()
    records.clear()
    session.execute(update(User).values(hashed_password="new-private"))
    session.execute(update(User.__table__).values(hashed_password="newer-private"))
    assert [r.changes for r in records] == [[{"field": "hashed_password", "new": "[redacted]"}]] * 2


@pytest.mark.parametrize("by_name", [False, True])
def test_manual_bulk_redaction(credential_session, by_name):
    session, records = credential_session
    record_bulk_audit(
        session, "User" if by_name else User, "bulk_updated", ["1"], {"hashed_password": "private"}
    )
    assert records[0].changes == [{"field": "hashed_password", "new": "[redacted]"}]


@pytest.mark.parametrize("cls", TOKENS)
def test_token_identity_redacted_on_update_delete_and_bulk(credential_session, cls):
    session, records = credential_session
    user = User(email="token-owner@test")
    session.add(user)
    session.flush()
    token = cls(token="private", user_id=user.id, expires_at=datetime.now(UTC))
    session.add(token)
    session.flush()
    records.clear()
    token.expires_at = datetime(2030, 1, 1, tzinfo=UTC)
    session.flush()
    session.execute(update(cls).values(expires_at=datetime(2031, 1, 1, tzinfo=UTC)))
    record_bulk_audit(session, cls.__name__, "bulk_updated", ["private"])
    session.execute(delete(cls))
    assert len(records) == 4
    assert all(r.entity_id == "[redacted]" for r in records)
