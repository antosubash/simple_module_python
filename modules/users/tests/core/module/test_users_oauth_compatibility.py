"""Legacy duplicate OAuth identities must be listed without changing links (#1153)."""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from users.module import UsersModule


@pytest.mark.parametrize("duplicates", [False, True])
async def test_oauth_identity_compatibility_lists_every_conflict(duplicates):
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("CREATE TABLE users_user (id TEXT, email TEXT)"))
            await conn.execute(
                sa.text(
                    "INSERT INTO users_user VALUES "
                    "('user-a', 'alice@example.com'), ('user-b', 'bob@example.com')"
                )
            )
            await conn.execute(
                sa.text(
                    "CREATE TABLE users_oauth_account "
                    "(id TEXT, user_id TEXT, oauth_name TEXT, account_id TEXT)"
                )
            )
            # More than the email check's display cap: no OAuth conflict may be hidden.
            for index in range(21):
                for owner in ["a", "b"] if duplicates else ["a"]:
                    await conn.execute(
                        sa.text("INSERT INTO users_oauth_account VALUES (:id, :user, :name, :sub)"),
                        {
                            "id": f"link-{index}-{owner}",
                            "user": f"user-{owner}",
                            "name": "microsoft",
                            "sub": f"subject-{index}",
                        },
                    )
            # The same account_id at another provider is a different identity.
            await conn.execute(
                sa.text(
                    "INSERT INTO users_oauth_account VALUES "
                    "('other', 'user-b', 'github', 'subject-0')"
                )
            )
        async with async_sessionmaker(engine)() as db:
            issues = await UsersModule().check_data_compatibility(db)
            assert bool(issues) is duplicates
            if duplicates:
                report = "\n".join(issue.message for issue in issues)
                remediation = "\n".join(issue.remediation_text or "" for issue in issues)
                assert all(issue.severity == "error" for issue in issues)
                assert all(issue.upgrade_id == "users.unique_oauth_identity_v1" for issue in issues)
                for index in range(21):
                    assert f"subject-{index!s}" in report
                for value in (
                    "microsoft",
                    "alice@example.com",
                    "bob@example.com",
                    "user-a",
                    "user-b",
                ):
                    assert value in report
                assert "Linked sign-ins" in remediation
                assert "Remove" in remediation
                assert "Edit" in remediation
            assert await db.scalar(sa.text("SELECT count(*) FROM users_oauth_account")) == (
                43 if duplicates else 22
            )
    finally:
        await engine.dispose()


async def test_duplicate_links_on_one_user_are_also_incompatible():
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("CREATE TABLE users_user (id TEXT, email TEXT)"))
            await conn.execute(sa.text("INSERT INTO users_user VALUES ('u', 'user@example.com')"))
            await conn.execute(
                sa.text(
                    "CREATE TABLE users_oauth_account "
                    "(id TEXT, user_id TEXT, oauth_name TEXT, account_id TEXT)"
                )
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO users_oauth_account VALUES "
                    "('link-a', 'u', 'github', 'subject'), ('link-b', 'u', 'github', 'subject')"
                )
            )
        async with async_sessionmaker(engine)() as db:
            issues = await UsersModule().check_data_compatibility(db)
            assert issues and issues[0].severity == "error"
            assert "link-a" in issues[0].message and "link-b" in issues[0].message
    finally:
        await engine.dispose()
