"""``make doctor`` reports SM010 and SM011 from the database it points at (#895)."""

from __future__ import annotations

import pytest
from _alembic_project import sqlite_database, write_alembic_project
from simple_module_core import ModuleBase, ModuleMeta, _migration_doctor
from simple_module_core import __main__ as doctor

_STAMP = "CREATE TABLE alembic_version (version_num VARCHAR(32))"


class _Module(ModuleBase):
    meta = ModuleMeta(name="Orders")


@pytest.fixture
def run_doctor(tmp_path, monkeypatch, capsys):
    """Run ``main()`` over one module declaring ``orders_order`` and ``orders_line``."""
    monkeypatch.setattr(doctor, "discover_modules", lambda strict: [_Module()])
    monkeypatch.setattr(doctor, "find_env_file", lambda: tmp_path / ".env")
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.setattr(doctor, "run_diagnostics", lambda *a, **kw: [])
    monkeypatch.setattr(
        _migration_doctor, "module_table_names", lambda modules: {"orders_order", "orders_line"}
    )

    def run(url: str) -> tuple[int, str]:
        monkeypatch.setenv("SM_DATABASE_URL", url)
        code = doctor.main()
        return code, capsys.readouterr().err

    return run


def test_db_doctor_reports_a_table_no_migration_creates(tmp_path, run_doctor):
    write_alembic_project(tmp_path, ["a:", "b:"])
    url = sqlite_database(
        tmp_path / "app.db",
        _STAMP,
        "INSERT INTO alembic_version VALUES ('a'), ('b')",
        "CREATE TABLE orders_order (id INTEGER)",
    )

    code, err = run_doctor(url)

    assert code == 0
    assert "SM011" in err
    assert "orders_line" in err
    assert "orders_order" not in err
    assert "SM010" not in err


def test_db_doctor_fails_on_a_database_behind_head(tmp_path, run_doctor):
    # The CLI's fallback location: host/alembic.ini under the project root.
    write_alembic_project(tmp_path / "host", ["a:", "a2:a", "b:"])
    url = sqlite_database(
        tmp_path / "app.db", _STAMP, "INSERT INTO alembic_version VALUES ('a'), ('b')"
    )

    code, err = run_doctor(url)

    assert code == 1
    assert "SM010" in err
    assert "missing heads 'a2'" in err
    # Behind head the table may only be in a pending revision.
    assert "SM011" not in err


def test_db_doctor_warns_on_a_missing_database(tmp_path, run_doctor):
    write_alembic_project(tmp_path, ["a:"])
    path = tmp_path / "app.db"

    code, err = run_doctor(f"sqlite+aiosqlite:///{path}")

    assert code == 0
    assert "SM010" in err
    assert "never been migrated" in err
    assert not path.exists()


def test_db_doctor_warns_on_an_unreadable_database(tmp_path, run_doctor):
    write_alembic_project(tmp_path, ["a:"])

    # A directory exists but cannot be opened as a SQLite database.
    code, err = run_doctor(f"sqlite+aiosqlite:///{tmp_path}")

    assert code == 0
    assert "SM010" in err
    assert "could not read the migration state" in err.lower()


def test_db_doctor_skips_without_an_alembic_project(tmp_path, run_doctor):
    code, err = run_doctor(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")

    assert code == 0
    assert "SM010" not in err
    assert "SM011" not in err


def test_db_doctor_anchors_a_relative_sqlite_url_at_the_project_root(
    tmp_path, monkeypatch, run_doctor
):
    # The app resolves ./app.db against the project root, not the cwd; doctor must too.
    write_alembic_project(tmp_path, ["a:"])
    sqlite_database(tmp_path / "app.db", _STAMP, "INSERT INTO alembic_version VALUES ('a')")
    (tmp_path / "host").mkdir()
    monkeypatch.chdir(tmp_path / "host")

    code, err = run_doctor("sqlite+aiosqlite:///./app.db")

    assert code == 0
    assert "never been migrated" not in err
    assert not (tmp_path / "host" / "app.db").exists()
