"""OAuth identity uniqueness upgrades refuse bad rows and round-trip (#1153)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def _migration():
    path = Path(__file__).resolve().parents[5] / "host/migrations/versions"
    spec = importlib.util.spec_from_file_location(
        "oauth_identity_migration", path / "b1153e9c7b62_users_unique_oauth_identity.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.parametrize("duplicate_owner", [None, "u1", "u2"])
def test_oauth_identity_migration_refuses_duplicates_or_roundtrips(duplicate_owner):
    migration = _migration()
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE users_user (id TEXT PRIMARY KEY, email TEXT)"))
            conn.execute(
                sa.text(
                    "INSERT INTO users_user VALUES ('u1', 'alice@example.com'), "
                    "('u2', 'bob@example.com')"
                )
            )
            conn.execute(
                sa.text(
                    "CREATE TABLE users_oauth_account (id TEXT PRIMARY KEY, user_id TEXT, "
                    "oauth_name TEXT NOT NULL, account_id TEXT NOT NULL, access_token TEXT)"
                )
            )
            insert = sa.text(
                "INSERT INTO users_oauth_account VALUES "
                "(:id, :user, :provider, 'subject', 'preserved-token')"
            )
            conn.execute(insert, {"id": "first", "user": "u1", "provider": "github"})
            if duplicate_owner:
                conn.execute(insert, {"id": "extra", "user": duplicate_owner, "provider": "github"})
            before = conn.execute(sa.text("SELECT * FROM users_oauth_account ORDER BY id")).all()
            with Operations.context(MigrationContext.configure(conn)):
                if duplicate_owner:
                    with pytest.raises(RuntimeError) as error:
                        migration.upgrade()
                    message = str(error.value)
                    for value in (
                        "github",
                        "subject",
                        "alice@example.com",
                        "u1",
                        "Edit",
                        "Linked sign-ins",
                        "Remove",
                    ):
                        assert value in message
                    if duplicate_owner == "u2":
                        assert "bob@example.com" in message and "u2" in message
                    assert "preserved-token" not in message
                    # Failure precedes DDL: no partial constraint or automatic deletion.
                    assert not sa.inspect(conn).get_unique_constraints("users_oauth_account")
                else:
                    migration.upgrade()
                    conn.execute(insert, {"id": "other", "user": "u2", "provider": "microsoft"})
                    conn.execute(sa.text("DELETE FROM users_oauth_account WHERE id='other'"))
                    with pytest.raises(IntegrityError):
                        conn.execute(insert, {"id": "extra", "user": "u2", "provider": "github"})
                    migration.downgrade()
                    conn.execute(insert, {"id": "extra", "user": "u2", "provider": "github"})
                    conn.execute(sa.text("DELETE FROM users_oauth_account WHERE id='extra'"))
                    migration.upgrade()
                assert (
                    conn.execute(sa.text("SELECT * FROM users_oauth_account ORDER BY id")).all()
                    == before
                )
    finally:
        engine.dispose()


def test_migration_duplicate_report_is_bounded():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE users_user (id TEXT, email TEXT)"))
            conn.execute(sa.text("INSERT INTO users_user VALUES ('u', 'alice@example.com')"))
            conn.execute(
                sa.text(
                    "CREATE TABLE users_oauth_account "
                    "(id TEXT, user_id TEXT, oauth_name TEXT, account_id TEXT)"
                )
            )
            conn.execute(
                sa.text("INSERT INTO users_oauth_account VALUES (:id, 'u', 'github', 'subject')"),
                [{"id": f"link-{index:02}"} for index in range(100)],
            )
            with (
                Operations.context(MigrationContext.configure(conn)),
                pytest.raises(RuntimeError) as error,
            ):
                _migration().upgrade()
            message = str(error.value)
            assert message.count("(user ") == 20
            assert "more" in message.lower()
            assert "link-19" in message and "link-20" not in message
            assert conn.scalar(sa.text("SELECT count(*) FROM users_oauth_account")) == 100
            assert not sa.inspect(conn).get_unique_constraints("users_oauth_account")
    finally:
        engine.dispose()
