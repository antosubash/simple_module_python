"""The default tenant browse page should not sort the tenant's whole bucket."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from file_storage.models import StoredFile
from file_storage.queries import order_clauses

_INDEX = "ix_file_storage_stored_file_tenant_browse"


def test_default_browse_uses_ordered_index():
    engine = sa.create_engine("sqlite://")
    table = StoredFile.__table__
    query = (
        sa.select(table.c.id)
        .where(table.c.tenant_id == "tenant", table.c.is_deleted.is_(False))
        .order_by(*order_clauses("-created_at"))
        .limit(25)
    )
    sql = str(query.compile(engine, compile_kwargs={"literal_binds": True}))
    with engine.begin() as conn:
        table.create(conn)
        plan = conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql).all()
    assert _INDEX in str(plan)
    assert "TEMP B-TREE" not in str(plan)


def test_browse_index_migration_roundtrip():
    path = (
        Path(__file__).resolve().parents[3]
        / "host/migrations/versions/f6c2d4e8b109_file_storage_browse_index.py"
    )
    spec = importlib.util.spec_from_file_location("browse_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE file_storage_stored_file "
            "(id INTEGER PRIMARY KEY, tenant_id TEXT, is_deleted BOOLEAN, created_at TEXT)"
        )
        conn.exec_driver_sql(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000) "
            "INSERT INTO file_storage_stored_file SELECT x, 'tenant', 0, printf('%06d', x) FROM n"
        )
        sql = (
            "SELECT id FROM file_storage_stored_file WHERE tenant_id='tenant' AND is_deleted=0 "
            "ORDER BY created_at DESC, id ASC LIMIT 25"
        )

        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            rows = conn.exec_driver_sql(sql).scalars().all()
            assert rows == list(range(1000, 975, -1))
            plan = conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql).all()
            assert _INDEX in str(plan) and "TEMP B-TREE" not in str(plan)
            migration.downgrade()
        assert _INDEX not in {
            i["name"] for i in sa.inspect(conn).get_indexes("file_storage_stored_file")
        }
