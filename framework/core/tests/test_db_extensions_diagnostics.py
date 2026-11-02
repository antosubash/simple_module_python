"""SM029: a module declaring Postgres extensions on a SQLite database (GH #458)."""

from __future__ import annotations

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics import DiagnosticLevel, run_diagnostics


class _PlainModule(ModuleBase):
    meta = ModuleMeta(name="plain")


class _TreeModule(ModuleBase):
    meta = ModuleMeta(name="tree")

    def db_extensions(self) -> list[str]:
        return ["ltree", "pg_trgm"]


def test_hook_defaults_to_no_extensions():
    assert _PlainModule().db_extensions() == []


def _sm029(dialect: str | None, *modules: ModuleBase):
    return [
        d for d in run_diagnostics(list(modules), database_dialect=dialect) if d.code == "SM029"
    ]


def test_sqlite_reports_info_naming_module_and_extensions():
    (diag,) = _sm029("sqlite", _PlainModule(), _TreeModule())

    assert diag.level == DiagnosticLevel.INFO
    assert diag.module_name == "tree"
    assert "ltree" in diag.message and "pg_trgm" in diag.message


def test_postgres_and_unknown_dialect_are_silent():
    assert _sm029("postgresql", _TreeModule()) == []
    assert _sm029(None, _TreeModule()) == []


def test_module_without_extensions_is_silent():
    assert _sm029("sqlite", _PlainModule()) == []
