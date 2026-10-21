"""Migration ``d7b3a9e5c1f2`` moves ``users.*`` mailer keys to ``mail.*`` (GH #496)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

BEFORE = "c8e4f1a2b6d9"
REVISION = "d7b3a9e5c1f2"
SCRIPTS = Path(__file__).resolve().parents[3] / "host" / "migrations"

pytestmark = pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")

_INSERT = sa.text(
    "INSERT INTO settings_setting (scope, scope_id, key, value, value_type, created_at,"
    " updated_at) VALUES (:scope, :scope_id, :key, :value, 'string', CURRENT_TIMESTAMP,"
    " CURRENT_TIMESTAMP)"
)


@pytest.fixture
def migrate(tmp_path, monkeypatch):
    db_file = tmp_path / "migrate.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    config = Config()
    config.set_main_option("script_location", str(SCRIPTS))
    engine = sa.create_engine(f"sqlite:///{db_file}")
    yield config, engine
    engine.dispose()


def _seed(engine, rows: list[tuple[str, str, str, str]]) -> None:
    with engine.begin() as conn:
        for scope, scope_id, key, value in rows:
            conn.execute(
                _INSERT, {"scope": scope, "scope_id": scope_id, "key": key, "value": value}
            )


def _rows(engine) -> set[tuple[str, str]]:
    with engine.connect() as conn:
        return {(k, v) for k, v in conn.execute(sa.text("SELECT key, value FROM settings_setting"))}


def test_upgrade_renames_and_downgrade_reverses(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    _seed(
        engine,
        [
            ("system", "", "users.mailer", "smtp"),
            ("system", "", "users.smtp_host", "h"),
            ("system", "", "users.smtp_port", "25"),
            ("system", "", "users.smtp_username", "u"),
            ("system", "", "users.smtp_password", "p"),
            ("system", "", "users.smtp_from", "f@x"),
            ("system", "", "users.smtp_tls", "False"),
            ("system", "", "users.allow_signup", "True"),
        ],
    )
    command.upgrade(config, REVISION)
    assert _rows(engine) == {
        ("mail.backend", "smtp"),
        ("mail.smtp_host", "h"),
        ("mail.smtp_port", "25"),
        ("mail.smtp_username", "u"),
        ("mail.smtp_password", "p"),
        ("mail.smtp_from", "f@x"),
        ("mail.smtp_tls", "False"),
        ("users.allow_signup", "True"),
    }

    command.downgrade(config, BEFORE)
    assert ("users.mailer", "smtp") in _rows(engine)
    assert ("users.smtp_host", "h") in _rows(engine)
    assert not any(k.startswith("mail.") for k, _ in _rows(engine))


def test_an_existing_mail_row_wins(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    _seed(
        engine,
        [
            ("system", "", "users.smtp_host", "old"),
            ("system", "", "mail.smtp_host", "new"),
        ],
    )
    command.upgrade(config, REVISION)
    assert _rows(engine) == {("mail.smtp_host", "new")}


def test_only_system_scope_rows_move(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    _seed(engine, [("tenant", "t1", "users.smtp_host", "tenant-host")])
    command.upgrade(config, REVISION)
    assert _rows(engine) == {("users.smtp_host", "tenant-host")}


def test_an_empty_table_is_a_no_op(migrate):
    config, engine = migrate
    command.upgrade(config, REVISION)
    command.downgrade(config, BEFORE)
    assert _rows(engine) == set()
