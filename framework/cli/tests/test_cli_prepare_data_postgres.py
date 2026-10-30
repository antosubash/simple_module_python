"""Frozen recipes and semantic recognition against PostgreSQL (#711)."""

import runpy

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from simple_module_cli.cli import app
from typer.testing import CliRunner

pytestmark = pytest.mark.postgres


def _revision(alembic_host, upgrade):
    _, versions = alembic_host
    result = CliRunner().invoke(app, ["migrations", "prepare", upgrade, "--head", "local"])
    assert result.exit_code == 0, result.output
    return runpy.run_path(str(next(p for p in versions.glob("*.py") if p.name != "local.py")))


async def test_cli_postgres_token_recipe_and_equivalent_port(db_session, alembic_host):
    from users.module import UsersModule

    revision = _revision(alembic_host, "users.hashed_bearer_tokens_v1")
    conn = await db_session.connection()
    await conn.execute(
        sa.text(
            "CREATE TEMP TABLE users_access_token (token VARCHAR(43) PRIMARY KEY) ON COMMIT DROP"
        )
    )
    await conn.execute(
        sa.text("CREATE TEMP TABLE users_refresh_token (token UUID PRIMARY KEY) ON COMMIT DROP")
    )
    await conn.execute(sa.text("INSERT INTO users_access_token VALUES ('plaintext')"))
    await conn.execute(
        sa.text("INSERT INTO users_refresh_token VALUES ('12345678-1234-1234-1234-123456789abc')")
    )
    assert (await UsersModule().check_data_compatibility(db_session))[0].severity == "error"

    def apply(sync, direction):
        with Operations.context(MigrationContext.configure(sync)):
            revision[direction]()

    await conn.run_sync(apply, "upgrade")
    assert await UsersModule().check_data_compatibility(db_session) == []
    for name in ["refresh", "access"]:
        assert await conn.scalar(sa.text(f"SELECT count(*) FROM users_{name}_token")) == 0
        await conn.execute(
            sa.text(f"INSERT INTO users_{name}_token VALUES (:token)"), {"token": "a" * 64}
        )
    assert await UsersModule().check_data_compatibility(db_session) == []
    await conn.run_sync(apply, "downgrade")
    for name in ["refresh", "access"]:
        assert await conn.scalar(sa.text(f"SELECT count(*) FROM users_{name}_token")) == 0
    assert (await UsersModule().check_data_compatibility(db_session))[
        0
    ].upgrade_id == "users.hashed_bearer_tokens_v1"


async def test_cli_postgres_mail_target_wins(db_session, alembic_host):
    from mail.module import MailModule

    revision = _revision(alembic_host, "mail.settings_namespace_v1")
    conn = await db_session.connection()
    await conn.execute(
        sa.text(
            "CREATE TEMP TABLE settings_setting "
            "(scope TEXT, scope_id TEXT, key TEXT, value TEXT) ON COMMIT DROP"
        )
    )
    await conn.execute(
        sa.text(
            "INSERT INTO settings_setting VALUES "
            "('system', '', 'users.smtp_host', 'old'), "
            "('system', '', 'mail.smtp_host', 'new')"
        )
    )
    assert (await MailModule().check_data_compatibility(db_session))[0].severity == "warning"

    def upgrade(sync):
        with Operations.context(MigrationContext.configure(sync)):
            revision["upgrade"]()

    await conn.run_sync(upgrade)
    assert await MailModule().check_data_compatibility(db_session) == []
    assert (await conn.execute(sa.text("SELECT key, value FROM settings_setting"))).all() == [
        ("mail.smtp_host", "new")
    ]
