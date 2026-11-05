"""Default task order is index-backed, including NULL timestamps."""

from io import StringIO
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from background_tasks.models import TaskExecution
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

INDEX = "ix_background_tasks_task_execution_queued_order"


def test_default_order_uses_index_without_sort():
    engine = sa.create_engine("sqlite://")
    try:
        TaskExecution.__table__.create(engine)
        with engine.connect() as conn:
            plan = conn.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT id FROM background_tasks_task_execution "
                "ORDER BY queued_at IS NULL, queued_at DESC LIMIT 20"
            ).all()
        detail = " ".join(str(row) for row in plan)
        assert INDEX in detail
        assert "TEMP B-TREE" not in detail
    finally:
        engine.dispose()


def test_order_index_migration_roundtrip():
    root = Path(__file__).resolve().parents[3]
    script = ScriptDirectory.from_config(Config(str(root / "host/alembic.ini")))
    revision = script.get_revision("background_tasks@head")
    assert revision.module.revision == "c5d8e2f1a903"
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE background_tasks_task_execution (id TEXT, queued_at DATETIME)"
            )
            with Operations.context(MigrationContext.configure(conn)):
                revision.module.upgrade()
                definition = conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE name = ?", (INDEX,)
                ).scalar_one()
                model_index = next(i for i in TaskExecution.__table__.indexes if i.name == INDEX)
                assert definition == str(CreateIndex(model_index).compile(conn)).strip()
                revision.module.downgrade()
                assert (
                    conn.exec_driver_sql(
                        "SELECT count(*) FROM sqlite_master WHERE name = ?", (INDEX,)
                    ).scalar_one()
                    == 0
                )
                revision.module.upgrade()
    finally:
        engine.dispose()


def test_order_index_postgres_ddl():
    root = Path(__file__).resolve().parents[3]
    script = ScriptDirectory.from_config(Config(str(root / "host/alembic.ini")))
    revision = script.get_revision("c5d8e2f1a903")
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(context):
        revision.module.upgrade()
    expected = (
        f"CREATE INDEX {INDEX} ON background_tasks_task_execution "
        "((queued_at IS NULL), queued_at DESC)"
    )
    assert output.getvalue().strip() == expected + ";"
    model_index = next(i for i in TaskExecution.__table__.indexes if i.name == INDEX)
    assert str(CreateIndex(model_index).compile(dialect=postgresql.dialect())) == expected
