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


async def test_db_doctor_reports_unavailable_database(tmp_path):
    from simple_module_db.data_compatibility import database_compatibility_diagnostics

    findings = await database_compatibility_diagnostics(
        [], f"sqlite+aiosqlite:///{tmp_path}/missing/db"
    )
    assert len(findings) == 1
    assert findings[0].level == "error"
    assert "could not" in findings[0].message.lower()
