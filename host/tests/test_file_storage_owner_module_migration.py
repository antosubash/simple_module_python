"""Rolling back module ownership preserves SQLite's newest-first browse index."""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from simple_module_hosting.boot.migrations import ALEMBIC_DATABASE_URL_ATTRIBUTE


def test_one_revision_downgrade_preserves_descending_browse_index(tmp_path):
    database = tmp_path / "migration.db"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes[ALEMBIC_DATABASE_URL_ATTRIBUTE] = f"sqlite:///{database}"

    command.upgrade(config, "heads")
    with sqlite3.connect(database) as connection:
        assert "owner_module" in {
            row[1] for row in connection.execute("PRAGMA table_info(file_storage_stored_file)")
        }
        assert (
            "created_at DESC"
            in connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name = 'ix_file_storage_stored_file_tenant_browse'"
            ).fetchone()[0]
        )

    command.downgrade(config, "f999a1b2c3d4-1")

    with sqlite3.connect(database) as connection:
        assert "owner_module" not in {
            row[1] for row in connection.execute("PRAGMA table_info(file_storage_stored_file)")
        }
        assert (
            "(tenant_id, is_deleted, created_at DESC, id)"
            in connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name = 'ix_file_storage_stored_file_tenant_browse'"
            ).fetchone()[0]
        )
