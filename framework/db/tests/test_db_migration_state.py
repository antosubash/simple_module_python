"""Doctor reads the migration state from the database it points at (#895)."""

from _alembic_project import sqlite_database, write_alembic_project
from simple_module_db.migration_state import read_migration_state


async def test_db_migration_state_none_without_an_ini(tmp_path):
    assert await read_migration_state("sqlite+aiosqlite://", tmp_path / "alembic.ini") is None


async def test_db_migration_state_missing_file_is_not_created(tmp_path):
    ini = write_alembic_project(tmp_path, ["a:", "b:"])
    path = tmp_path / "app.db"

    state = await read_migration_state(f"sqlite+aiosqlite:///{path}", ini)

    assert state is not None
    assert state.heads == {"a", "b"}
    assert state.current == set()
    assert state.tables == set()
    assert not path.exists()


async def test_db_migration_state_reads_an_unstamped_database(tmp_path):
    ini = write_alembic_project(tmp_path, ["a:"])
    url = sqlite_database(tmp_path / "app.db", "CREATE TABLE orders_order (id INTEGER)")

    state = await read_migration_state(url, ini)

    assert state is not None
    assert state.current == set()
    assert state.tables == {"orders_order"}


async def test_db_migration_state_reads_current_heads(tmp_path):
    ini = write_alembic_project(tmp_path, ["a:", "a2:a", "b:"])
    url = sqlite_database(
        tmp_path / "app.db",
        "CREATE TABLE alembic_version (version_num VARCHAR(32))",
        "INSERT INTO alembic_version VALUES ('a'), ('b')",
    )

    state = await read_migration_state(url, ini)

    assert state is not None
    assert state.heads == {"a2", "b"}
    assert state.current == {"a", "b"}
    assert "alembic_version" in state.tables
