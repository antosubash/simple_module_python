"""Capture concrete changes, never SQL text pretending to be a resulting value."""

import pytest
from audit_log.entries.export import format_changes
from simple_module_db.auditing.audit import COMPUTED_BY_DATABASE, collect_audit_records
from sqlalchemy import create_engine, literal
from sqlalchemy.orm import Session, make_transient_to_detached
from users.models import User


@pytest.mark.parametrize("literal_change", [False, True])
def test_expression_updates_record_a_marker_and_preserve_literal_changes(literal_change):
    engine = create_engine("sqlite://")
    try:
        User.__table__.create(engine)
        with Session(engine, expire_on_commit=False) as session:
            user = User(email="sam@example.com", hashed_password="x", session_version=0)
            session.add(user)
            session.flush()
            user.session_version = User.session_version + 1
            if literal_change:
                user.full_name = "Sam"

            records = collect_audit_records(session)

            bump = {"field": "session_version", "old": 0, "new": COMPUTED_BY_DATABASE}
            name = {"field": "full_name", "old": None, "new": "Sam"}
            # The revocation stays on record, without SQL text as its value.
            assert [sorted(r.changes, key=lambda c: c["field"]) for r in records] == [
                [name, bump] if literal_change else [bump]
            ]
            session.flush()
            session.refresh(user, attribute_names=["session_version"])
            assert user.session_version == 1
    finally:
        engine.dispose()


def test_expression_values_on_creation_are_not_recorded():
    with Session() as session:
        user = User(email="sam@example.com", hashed_password="x")
        user.session_version = literal(1)
        session.add(user)

        records = collect_audit_records(session)

        assert len(records) == 1
        assert "session_version" not in {c["field"] for c in records[0].changes}
        assert {"field": "email", "new": "sam@example.com"} in records[0].changes


def test_literal_counter_updates_remain_audited():
    with Session() as session:
        user = User(email="sam@example.com", hashed_password="x", session_version=0)
        # Give the collector a persisted baseline without database IO.
        make_transient_to_detached(user)
        session.add(user)
        user.session_version = 1

        records = collect_audit_records(session)

        assert [r.changes for r in records] == [[{"field": "session_version", "old": 0, "new": 1}]]


def test_mapped_column_updates_record_a_computed_value():
    engine = create_engine("sqlite://")
    try:
        User.__table__.create(engine)
        with Session(engine, expire_on_commit=False) as session:
            user = User(email="sam@example.com", hashed_password="x", full_name="Sam")
            session.add(user)
            session.flush()
            user.full_name = User.email

            records = collect_audit_records(session)

            assert [r.changes for r in records] == [
                [{"field": "full_name", "old": "Sam", "new": COMPUTED_BY_DATABASE}]
            ]
            expected_csv = f'full_name: "Sam" → "{COMPUTED_BY_DATABASE}"'
            assert format_changes(records[0].changes) == expected_csv
            session.flush()
            session.refresh(user, attribute_names=["full_name"])
            assert user.full_name == "sam@example.com"
    finally:
        engine.dispose()


def test_expression_protocol_values_on_creation_are_not_recorded():
    class DatabaseValue:
        def __clause_element__(self):
            return literal(1)

    engine = create_engine("sqlite://")
    try:
        User.__table__.create(engine)
        with Session(engine, expire_on_commit=False) as session:
            user = User(email="sam@example.com", hashed_password="x")
            user.session_version = DatabaseValue()
            session.add(user)

            records = collect_audit_records(session)

            assert "session_version" not in {c["field"] for c in records[0].changes}
            session.flush()
            session.refresh(user, attribute_names=["session_version"])
            assert user.session_version == 1
    finally:
        engine.dispose()
