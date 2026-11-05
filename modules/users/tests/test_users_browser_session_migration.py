"""The users revision supports a local upgrade/downgrade/upgrade."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_browser_session_revision_roundtrip(monkeypatch):
    path = (
        Path(__file__).resolve().parents[3]
        / "host/migrations/versions/e805a1b2c3d4_users_browser_sessions.py"
    )
    spec = importlib.util.spec_from_file_location("browser_session_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users_user (id CHAR(36) PRIMARY KEY)"))
        monkeypatch.setattr(revision, "op", Operations(MigrationContext.configure(connection)))
        for _ in range(2):
            revision.upgrade()
            inspector = sa.inspect(connection)
            assert "users_revoked_session" in inspector.get_table_names()
            assert {index["name"] for index in inspector.get_indexes("users_revoked_session")} == {
                "ix_users_revoked_session_user_id",
                "ix_users_revoked_session_expires_at",
            }
            revision.downgrade()
            assert "users_revoked_session" not in sa.inspect(connection).get_table_names()
    engine.dispose()
