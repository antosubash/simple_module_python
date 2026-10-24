"""The hash migration invalidates plaintext credentials and round-trips (#626)."""

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_users_hash_migration_invalidates_tokens_in_both_directions():
    path = Path(__file__).resolve().parents[3] / "host/migrations/versions"
    spec = importlib.util.spec_from_file_location(
        "hash_migration", path / "a626b1c8d023_users_hash_bearer_tokens_at_rest.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    refresh = sa.Table(
        "users_refresh_token",
        metadata,
        sa.Column("token", sa.Uuid(), primary_key=True),
        sa.Column("family_id", sa.Uuid(), nullable=False, index=True),
    )
    access = sa.Table(
        "users_access_token", metadata, sa.Column("token", sa.String(43), primary_key=True)
    )
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(refresh.insert().values(token=uuid.uuid4(), family_id=uuid.uuid4()))
            connection.execute(access.insert().values(token="plaintext-access"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                for table in (refresh, access):
                    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 0
                    column = sa.inspect(connection).get_columns(table.name)[0]
                    assert column["type"].length == 64
                connection.execute(
                    sa.text(
                        "INSERT INTO users_refresh_token (token, family_id) "
                        "VALUES (:token, :family)"
                    ),
                    {"token": "a" * 64, "family": uuid.uuid4().hex},
                )
                connection.execute(
                    sa.text("INSERT INTO users_access_token (token) VALUES (:token)"),
                    {"token": "b" * 64},
                )
                migration.downgrade()
                for table in (refresh, access):
                    assert connection.scalar(sa.select(sa.func.count()).select_from(table)) == 0
                connection.execute(
                    refresh.insert().values(token=uuid.uuid4(), family_id=uuid.uuid4())
                )
                connection.execute(access.insert().values(token="new-plaintext"))
    finally:
        engine.dispose()
