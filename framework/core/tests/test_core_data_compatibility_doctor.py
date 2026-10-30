"""Both Doctor entry points report upgrade ids and return a failing status (#711)."""

import pytest
import sqlalchemy as sa
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core import __main__ as doctor
from simple_module_core.data_compatibility import DataCompatibilityIssue


@pytest.mark.parametrize("entrypoint", ["make", "smpy"])
def test_core_doctor_reports_semantic_data_errors(tmp_path, monkeypatch, capsys, entrypoint):
    path = tmp_path / "doctor.db"
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(sa.text("INSERT INTO alembic_version VALUES ('local')"))
    engine.dispose()

    class Module(ModuleBase):
        meta = ModuleMeta(name="Example")

        async def check_data_compatibility(self, db):
            assert await db.scalar(sa.text("SELECT version_num FROM alembic_version")) == "local"
            return [
                DataCompatibilityIssue(
                    upgrade_id="example.v1", message="Upgrade required", severity="error"
                )
            ]

    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    monkeypatch.setattr(doctor, "discover_modules", lambda strict: [Module()])
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.setattr(doctor, "run_diagnostics", lambda *a, **kw: [])
    if entrypoint == "make":
        assert doctor.main() == 1
        output = capsys.readouterr().err
    else:
        from simple_module_cli.cli import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(app, ["doctor"])
        assert result.exit_code == 1
        output = result.output
    assert "example.v1" in output
    assert "smpy migrations prepare example.v1" in output
