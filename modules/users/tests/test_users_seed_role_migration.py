"""Migration ``b5018b617142`` seeds the ``user`` role (GH #488 review).

Without it a fresh install has no ``user`` role, so the role a signup is given
is looked up, not found, and every self-registered account holds nothing. An
install that already has users is left alone: there a missing role may be an
admin's deliberate deletion, which an upgrade must not undo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from users.constants import USER_ROLE_DESCRIPTION, USER_ROLE_ID, USER_ROLE_NAME

BEFORE = "e878882924e7"
REVISION = "b5018b617142"
SCRIPTS = Path(__file__).resolve().parents[3] / "host" / "migrations"

pytestmark = pytest.mark.filterwarnings("ignore:Skipped unsupported reflection")


@pytest.fixture
def migrate(tmp_path, monkeypatch):
    db_file = tmp_path / "migrate.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    # No ini file: env.py would run ``fileConfig`` and disable existing loggers.
    config = Config()
    config.set_main_option("script_location", str(SCRIPTS))
    engine = sa.create_engine(f"sqlite:///{db_file}")
    yield config, engine
    engine.dispose()


def _roles(engine) -> list[tuple[str, str, str | None]]:
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(sa.text("SELECT id, name, description FROM users_role"))
        ]


def test_a_fresh_install_has_the_user_role(migrate):
    config, engine = migrate
    command.upgrade(config, REVISION)
    assert _roles(engine) == [(str(USER_ROLE_ID), USER_ROLE_NAME, USER_ROLE_DESCRIPTION)]


def test_an_existing_user_role_is_left_alone_and_downgrade_keeps_it(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO users_role (id, name, description) VALUES (:id, 'user', 'mine')"),
            {"id": "11111111-1111-1111-1111-111111111111"},
        )
    command.upgrade(config, REVISION)
    command.downgrade(config, BEFORE)
    assert _roles(engine) == [("11111111-1111-1111-1111-111111111111", "user", "mine")]


def test_an_install_with_users_and_no_user_role_is_not_seeded(migrate):
    config, engine = migrate
    command.upgrade(config, BEFORE)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users_user (id, email, hashed_password, is_active,"
                " is_superuser, is_verified) VALUES (:id, 'a@example.com', 'x', 1, 0, 1)"
            ),
            {"id": "22222222-2222-2222-2222-222222222222"},
        )
    command.upgrade(config, REVISION)
    assert _roles(engine) == []
