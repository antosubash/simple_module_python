"""Only obsolete system mail keys require a host revision (#711)."""

import pytest
from mail.module import MailModule
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.parametrize(
    ("scope", "scope_id", "key", "expected"),
    [
        ("system", "", "users.smtp_password", True),
        ("system", "", "users.mailer", True),
        ("tenant", "one", "users.smtp_host", False),
        ("system", "other", "users.mailer", False),
        ("system", "", "mail.smtp_host", False),
        ("system", "", "users.unrelated", False),
    ],
)
async def test_mail_obsolete_system_keys(scope, scope_id, key, expected):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE settings_setting (scope TEXT, scope_id TEXT, key TEXT)")
            )
            await conn.execute(
                text("INSERT INTO settings_setting VALUES (:scope, :scope_id, :key)"),
                {"scope": scope, "scope_id": scope_id, "key": key},
            )
        async with async_sessionmaker(engine)() as db:
            issues = await MailModule().check_data_compatibility(db)
            assert bool(issues) is expected
            if expected:
                assert issues[0].upgrade_id == "mail.settings_namespace_v1"
                assert issues[0].severity == "warning"
    finally:
        await engine.dispose()
