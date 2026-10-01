"""Migration ``c7f2d9a41e83``: existing files are back-filled into the default tenant.

Runs the real Alembic chain against a throwaway SQLite file: rows written
before the migration keep their key and land in ``DEFAULT_TENANT_ID`` (which is
also the platform owner, so pre-existing branding images stay servable), the
unique key widens to ``(tenant_id, key)``, and the downgrade puts it all back.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from simple_module_db import DEFAULT_TENANT_ID
from sqlalchemy.exc import IntegrityError

BEFORE = "b5d3f08a6e17"
REVISION = "c7f2d9a41e83"
TABLE = "file_storage_stored_file"
SCRIPTS = Path(__file__).resolve().parents[3] / "host" / "migrations"


@pytest.fixture
def migrate(tmp_path, monkeypatch):
    db_file = tmp_path / "migrate.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    # No ini file on purpose: env.py runs ``fileConfig`` for one, which
    # disables every logger already created and breaks later caplog tests.
    config = Config()
    config.set_main_option("script_location", str(SCRIPTS))
    engine = sa.create_engine(f"sqlite:///{db_file}")
    yield config, engine
    engine.dispose()


def _insert(conn, key: str, **extra) -> None:
    conn.execute(
        sa.text(
            f"INSERT INTO {TABLE} (id, key, filename, content_type, size_bytes, backend,"
            " checksum_sha256, extra_metadata, is_deleted"
            + "".join(f", {k}" for k in extra)
            + ") VALUES (:id, :key, 'f.txt', 'text/plain', 1, 'filesystem', :sum, '{}', 0"
            + "".join(f", :{k}" for k in extra)
            + ")"
        ),
        {"id": uuid.uuid4().hex, "key": key, "sum": "0" * 64, **extra},
    )


def _unique_indexes(engine) -> list[list[str]]:
    return sorted(
        ix["column_names"] for ix in sa.inspect(engine).get_indexes(TABLE) if ix["unique"]
    )


# An earlier revision in the chain reflects ``users_user`` under batch mode.
@pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")
def test_upgrade_backfills_and_downgrade_restores(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    with engine.begin() as conn:
        _insert(conn, "2026/01/01/old.txt")

    command.upgrade(config, REVISION)

    with engine.begin() as conn:
        rows = conn.execute(sa.text(f"SELECT key, tenant_id FROM {TABLE}")).all()
        assert [tuple(r) for r in rows] == [("2026/01/01/old.txt", DEFAULT_TENANT_ID)]
        # The same key is now fine in another tenant...
        _insert(conn, "2026/01/01/old.txt", tenant_id="other")
    assert _unique_indexes(engine) == [["tenant_id", "key"]]
    columns = {c["name"]: c for c in sa.inspect(engine).get_columns(TABLE)}
    assert columns["tenant_id"]["nullable"] is False
    # ...but not twice in the same one.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert(conn, "2026/01/01/old.txt", tenant_id="other")

    with engine.begin() as conn:
        conn.execute(sa.text(f"DELETE FROM {TABLE} WHERE tenant_id = 'other'"))
    command.downgrade(config, BEFORE)

    assert "tenant_id" not in {c["name"] for c in sa.inspect(engine).get_columns(TABLE)}
    assert _unique_indexes(engine) == [["key"]]
    with engine.begin() as conn:
        assert conn.execute(sa.text(f"SELECT key FROM {TABLE}")).scalars().all() == [
            "2026/01/01/old.txt"
        ]
