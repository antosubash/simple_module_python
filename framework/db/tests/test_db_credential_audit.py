"""Credential changes remain visible without recording their values."""

from datetime import UTC, datetime

import pytest
from simple_module_db.audit import collect_audit_records
from simple_module_db.leases import LeaseRow
from simple_module_db.stored_settings import Setting
from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "key,value,value_type,expected",
    [
        ("mail.smtp_password", "private", "string", "[redacted]"),
        ("host.secret_key", "private", "int", "[redacted]"),
        ("mail.url", "smtp://user:private@localhost", "string", "[redacted]"),
        ("mail.port", "587", "int", "587"),
        ("users.reset_password_token_lifetime_seconds", "3600", "int", "3600"),
    ],
)
def test_setting_create_redaction(key, value, value_type, expected):
    with Session() as session:
        session.add(Setting(key=key, value=value, value_type=value_type))
        record = collect_audit_records(session)[0]
        assert next(c["new"] for c in record.changes if c["field"] == "value") == expected


@pytest.fixture
def credential_session():
    from simple_module_db.listeners import attach_session_listeners
    from simple_module_db.query_filter import EngineTenancy, bind_engine_policy
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    records = []
    policy = EngineTenancy(
        tenant_strict=False, audit_callback=lambda session, batch: records.extend(batch)
    )
    bind_engine_policy(engine, policy)

    class AuditSession(Session):
        pass

    attach_session_listeners(AuditSession)
    try:
        Setting.metadata.create_all(engine)
        with AuditSession(engine) as session:
            yield session, records
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["setting", "renamed", "url"])
def test_credential_update_redacts_both_sides(credential_session, kind):
    session, records = credential_session
    entity = Setting(
        key="mail.url" if kind == "url" else "mail.smtp_password",
        value="smtp://u:private@localhost" if kind == "url" else "old-private",
    )
    field = "value"
    session.add(entity)
    session.flush()
    records.clear()
    setattr(entity, field, "public" if kind == "url" else "new-private")
    if kind == "renamed":
        entity.key = "mail.label"
    session.flush()
    assert next(c for c in records[0].changes if c["field"] == field) == {
        "field": field,
        "old": "[redacted]",
        "new": "[redacted]",
    }


@pytest.mark.parametrize("core", [False, True])
def test_bulk_credentials_redacted(credential_session, core):
    from sqlalchemy import update

    session, records = credential_session
    session.add(Setting(key="mail.smtp_password", value="old-private"))
    session.flush()
    records.clear()
    session.execute(update(Setting.__table__ if core else Setting).values(value="new-private"))
    assert records[0].changes == [{"field": "value", "new": "[redacted]"}]


@pytest.mark.parametrize("by_name", [False, True])
def test_manual_bulk_redaction(credential_session, by_name):
    from simple_module_db import record_bulk_audit

    session, records = credential_session
    record_bulk_audit(
        session, "Setting" if by_name else Setting, "bulk_updated", ["1"], {"value": "private"}
    )
    assert records[0].changes == [{"field": "value", "new": "[redacted]"}]


def test_nonsecret_setting_update_retains_values(credential_session):
    session, records = credential_session
    setting = Setting(key="mail.port", value="587", value_type="int")
    session.add(setting)
    session.flush()
    records.clear()
    setting.value = "465"
    session.flush()
    assert records[0].changes == [{"field": "value", "old": "587", "new": "465"}]


@pytest.mark.parametrize("core", [False, True])
def test_bulk_insert_and_summary_redaction(credential_session, monkeypatch, core):
    import simple_module_db.bulk_audit as bulk
    from sqlalchemy import insert, update

    session, records = credential_session
    target = Setting.__table__ if core else Setting
    session.execute(
        insert(target).values(
            key="mail.smtp_password",
            value="private",
            value_type="string",
            scope="system",
            scope_id="",
        )
    )
    assert next(c["new"] for c in records[0].changes if c["field"] == "value") == "[redacted]"
    records.clear()
    monkeypatch.setattr(bulk, "BULK_AUDIT_ID_CAP", 0)
    session.execute(update(target).values(value="new-private"))
    assert records[0].entity_id == "*"
    assert records[0].changes[0] == {"field": "value", "new": "[redacted]"}


def test_typed_setting_redaction():
    from pydantic import SecretStr
    from simple_module_core.secret_fields import register_typed_secrets
    from sqlmodel import SQLModel

    class CredentialSettings(SQLModel):
        credential: SecretStr

    register_typed_secrets("audit_test", CredentialSettings)
    with Session() as session:
        session.add(Setting(key="audit_test.credential", value="private"))
        changes = collect_audit_records(session)[0].changes
        assert next(c["new"] for c in changes if c["field"] == "value") == "[redacted]"


def test_manual_bulk_honors_field_exclusions(credential_session):
    from _audit_models import PartialExcludeModel
    from simple_module_db import record_bulk_audit

    session, records = credential_session
    record_bulk_audit(
        session,
        PartialExcludeModel,
        "bulk_updated",
        ["1"],
        {"password_hash": "private", "username": "visible"},
    )
    assert records[0].changes == [{"field": "username", "new": "visible"}]


def test_lease_ownership_value_is_redacted():
    with Session() as session:
        session.add(LeaseRow(name="audit", slot=0, holder="private", expires_at=datetime.now(UTC)))
        changes = collect_audit_records(session)[0].changes
        assert next(c["new"] for c in changes if c["field"] == "holder") == "[redacted]"
