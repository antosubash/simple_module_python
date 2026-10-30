"""Doctor checks semantic upgrades without importing host code (#711)."""

import pytest
from simple_module_core.data_compatibility import DataCompatibilityIssue
from simple_module_core.module import ModuleBase, ModuleMeta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.parametrize(
    ("migrated", "severity", "expected"),
    [
        (True, "error", "error"),
        (True, "warning", "warning"),
        (False, "error", None),
    ],
)
async def test_db_doctor_data_findings(tmp_path, migrated, severity, expected):
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    url = f"sqlite+aiosqlite:///{tmp_path / 'doctor.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            if migrated:
                await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
                await conn.execute(
                    text("INSERT INTO alembic_version VALUES ('host_local_revision')")
                )
    finally:
        await engine.dispose()

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            return [
                DataCompatibilityIssue(
                    upgrade_id="example.v1", message="Upgrade required", severity=severity
                )
            ]

    findings = await database_compatibility_diagnostics([Module()], url)
    if expected:
        assert len(findings) == 1
        assert findings[0].level == expected
        assert "example.v1" in findings[0].message
        assert "smpy migrations prepare example.v1" in findings[0].suggestion
    else:
        assert findings == []


async def test_db_doctor_skips_a_sqlite_file_that_does_not_exist(tmp_path):
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    path = tmp_path / "app.db"
    assert await database_compatibility_diagnostics([], f"sqlite+aiosqlite:///{path}") == []
    # Doctor must not leave an empty database behind.
    assert not path.exists()


async def test_db_doctor_warns_on_unreachable_database(tmp_path):
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    # A directory exists but cannot be opened as a SQLite database.
    findings = await database_compatibility_diagnostics([], f"sqlite+aiosqlite:///{tmp_path}")
    assert len(findings) == 1
    assert findings[0].level == "warning"
    assert "could not reach" in findings[0].message.lower()


async def test_db_doctor_fails_when_a_module_check_crashes(tmp_path):
    from simple_module_core.module import ModuleBase
    from simple_module_core.module_meta import ModuleMeta
    from simple_module_db.data_compatibility import database_compatibility_diagnostics
    from sqlalchemy import create_engine, text

    path = tmp_path / "app.db"
    with create_engine(f"sqlite:///{path}").begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('abc')"))

    class Broken(ModuleBase):
        meta = ModuleMeta(name="Broken")

        async def check_data_compatibility(self, db):
            raise KeyError("bug")

    findings = await database_compatibility_diagnostics([Broken()], f"sqlite+aiosqlite:///{path}")
    assert [f.level for f in findings] == ["error"]
    assert "KeyError" in findings[0].message
