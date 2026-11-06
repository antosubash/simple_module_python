"""Semantic token checks accept current baselines and equivalent ports (#711)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from users.module import UsersModule


@pytest.mark.parametrize(
    ("access_type", "refresh_type", "token", "incompatible"),
    [
        ("VARCHAR(64)", "VARCHAR(64)", None, False),
        ("VARCHAR(64)", "VARCHAR(64)", "a" * 64, False),
        ("VARCHAR(43)", "CHAR(32)", None, True),
        ("VARCHAR(64)", "VARCHAR(64)", "plaintext", True),
        ("VARCHAR(64)", "VARCHAR(64)", "z" * 64, True),
    ],
)
async def test_users_semantic_token_compatibility(access_type, refresh_type, token, incompatible):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            for name, kind in [("access", access_type), ("refresh", refresh_type)]:
                await conn.execute(text(f"CREATE TABLE users_{name}_token (token {kind})"))
                if token:
                    await conn.execute(
                        text(f"INSERT INTO users_{name}_token VALUES (:token)"), {"token": token}
                    )
        async with async_sessionmaker(engine)() as db:
            issues = await UsersModule().check_data_compatibility(db)
            assert bool(issues) is incompatible
            if incompatible:
                assert issues[0].upgrade_id == "users.hashed_bearer_tokens_v1"
                assert issues[0].severity == "error"
            if token:
                assert await db.scalar(text("SELECT token FROM users_access_token")) == token
    finally:
        await engine.dispose()


async def test_missing_token_tables_are_not_a_finding():
    # An unmigrated database is the migration check's problem; this must not
    # refuse a production boot on its own.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with async_sessionmaker(engine)() as db:
            assert await UsersModule().check_data_compatibility(db) == []
    finally:
        await engine.dispose()


async def test_plaintext_rows_behind_hashed_ones_are_found():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            for name in ("access", "refresh"):
                await conn.execute(text(f"CREATE TABLE users_{name}_token (token VARCHAR(64))"))
                for i in range(150):
                    await conn.execute(
                        text(f"INSERT INTO users_{name}_token VALUES (:t)"), {"t": f"{i:064x}"}
                    )
            await conn.execute(text("INSERT INTO users_access_token VALUES ('plaintext')"))
        async with async_sessionmaker(engine)() as db:
            assert await UsersModule().check_data_compatibility(db)
    finally:
        await engine.dispose()
