"""Case-insensitive email constraints and safe upgrades (#731)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from users.models import User
from users.module import UsersModule


@pytest.mark.parametrize("duplicates", [False, True])
async def test_users_duplicate_email_compatibility_is_read_only(duplicates):
    engine = create_async_engine("sqlite+aiosqlite://")
    emails = ["Alice@example.com", "alice@example.com"] if duplicates else ["Alice@example.com"]
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("CREATE TABLE users_user (email VARCHAR(320))"))
            for email in emails:
                await conn.execute(
                    sa.text("INSERT INTO users_user VALUES (:email)"), {"email": email}
                )
        async with async_sessionmaker(engine)() as db:
            issues = await UsersModule().check_data_compatibility(db)
            assert bool(issues) is duplicates
            if duplicates:
                assert issues[0].severity == "error"
                # Masked in logs; the full addresses never appear.
                assert "a***@example.com" in issues[0].message
                assert not any(email in issues[0].message for email in emails)
                assert "SELECT id, email FROM users_user" in issues[0].message
            assert (
                list((await db.execute(sa.text("SELECT email FROM users_user"))).scalars())
                == emails
            )
    finally:
        await engine.dispose()


def _migration():
    path = Path(__file__).resolve().parents[3] / "host/migrations/versions"
    spec = importlib.util.spec_from_file_location(
        "users_email_migration", path / "e731a1b2c3d4_users_unique_lower_email.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.parametrize("duplicates", [False, True])
def test_users_email_migration_refuses_duplicates_or_roundtrips(duplicates):
    migration = _migration()
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE users_user (email VARCHAR(320) NOT NULL)"))
            conn.execute(
                sa.text("CREATE INDEX ix_users_user_email_lower ON users_user (lower(email))")
            )
            conn.execute(sa.text("INSERT INTO users_user VALUES ('Alice@example.com')"))
            if duplicates:
                conn.execute(sa.text("INSERT INTO users_user VALUES ('alice@example.com')"))
            with Operations.context(MigrationContext.configure(conn)):
                if duplicates:
                    with pytest.raises(RuntimeError) as error:
                        migration.upgrade()
                    assert "a***@example.com" in str(error.value)
                    assert "lice@example.com" not in str(error.value)
                    assert conn.scalar(sa.text("SELECT count(*) FROM users_user")) == 2
                    # Refusal leaves the old index in place and accounts untouched.
                    assert "UNIQUE" not in conn.scalar(
                        sa.text(
                            "SELECT sql FROM sqlite_master WHERE name='ix_users_user_email_lower'"
                        )
                    )
                else:
                    migration.upgrade()
                    with pytest.raises(sa.exc.IntegrityError):
                        conn.execute(sa.text("INSERT INTO users_user VALUES ('alice@example.com')"))
                    migration.downgrade()
                    conn.execute(sa.text("INSERT INTO users_user VALUES ('alice@example.com')"))
                    conn.execute(sa.text("DELETE FROM users_user WHERE email='alice@example.com'"))
                    migration.upgrade()
                    assert (
                        conn.scalar(sa.text("SELECT email FROM users_user")) == "Alice@example.com"
                    )
    finally:
        engine.dispose()


def test_users_model_rejects_case_variant_email():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            User.__table__.create(conn)
            conn.execute(User.__table__.insert().values(email="Alice@example.com"))
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(User.__table__.insert().values(email="alice@example.com"))
    finally:
        engine.dispose()
