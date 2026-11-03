"""The refresh outcome migration round-trips and matches auth metadata."""

from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from auth.models import Base
from sqlalchemy import create_engine, inspect


def test_refresh_outcome_sqlite_roundtrip():
    root = Path(__file__).resolve().parents[3]
    script = ScriptDirectory.from_config(Config(str(root / "host/alembic.ini")))
    migration = script.get_revision("auth@head").module
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                migration.upgrade()
                assert compare_metadata(context, Base.metadata) == []
                migration.downgrade()
                assert inspect(conn).get_table_names() == []
                migration.upgrade()
                assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
