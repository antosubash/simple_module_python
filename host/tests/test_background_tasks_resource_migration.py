"""Resource-reference migration preserves legacy rows and roundtrips on SQLite."""

from importlib import import_module

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from background_tasks.models import TaskExecution
from sqlalchemy.exc import IntegrityError


def test_resource_reference_migration_roundtrip(tmp_path, monkeypatch):
    migration = import_module(
        "host.migrations.versions.b31a70971001_background_tasks_resource_reference"
    )
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE background_tasks_task_execution (id INTEGER PRIMARY KEY, "
            "task_name VARCHAR(255), owner_user_id VARCHAR(64))"
        )
        connection.exec_driver_sql(
            "INSERT INTO background_tasks_task_execution VALUES (1, 'demo.image', 'owner')"
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(
                MigrationContext.configure(
                    connection, opts={"target_metadata": TaskExecution.metadata}
                )
            ),
        )
        migration.upgrade()
        assert {
            item["name"]
            for item in sa.inspect(connection).get_check_constraints(
                "background_tasks_task_execution"
            )
        } == {"ck_background_tasks_task_execution_task_resource_pair"}
        row = connection.exec_driver_sql(
            "SELECT owner_user_id, resource_type, resource_id FROM background_tasks_task_execution"
        ).one()
        assert tuple(row) == ("owner", None, None)
        connection.exec_driver_sql(
            "UPDATE background_tasks_task_execution SET resource_type='demo.image', resource_id='7'"
        )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "UPDATE background_tasks_task_execution SET resource_id=NULL"
            )
        migration.downgrade()
        assert [
            col["name"]
            for col in sa.inspect(connection).get_columns("background_tasks_task_execution")
        ] == ["id", "task_name", "owner_user_id"]
        assert (
            connection.exec_driver_sql(
                "SELECT owner_user_id FROM background_tasks_task_execution"
            ).scalar_one()
            == "owner"
        )
    engine.dispose()
