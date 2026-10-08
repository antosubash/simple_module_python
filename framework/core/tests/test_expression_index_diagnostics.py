"""SM026: expression indexes SQLite cannot verify (GH #342)."""

from __future__ import annotations

import sqlalchemy as sa
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics import DiagnosticLevel, run_diagnostics
from simple_module_core.diagnostics._expression_index import (
    check_expression_indexes_unverifiable,
    find_expression_indexes,
)


def _tables() -> list[sa.Table]:
    md = sa.MetaData()
    return [
        sa.Table(
            "users_user",
            md,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("email", sa.String),
            sa.Index("ix_users_user_email_lower", sa.text("lower(email)")),
            sa.Index("ix_users_user_email", "email"),
        ),
        sa.Table("plain", md, sa.Column("id", sa.Integer, primary_key=True)),
    ]


def test_find_expression_indexes_ignores_plain_column_indexes():
    assert find_expression_indexes(_tables()) == [("users_user", "ix_users_user_email_lower")]


def test_function_expression_counts_as_expression():
    md = sa.MetaData()
    table = sa.Table(
        "t",
        md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String),
    )
    sa.Index("ix_t_name_lower", sa.func.lower(table.c.name))
    assert find_expression_indexes([table]) == [("t", "ix_t_name_lower")]


def test_sqlite_reports_info_naming_the_index():
    (diag,) = check_expression_indexes_unverifiable(_tables(), "sqlite", "users")

    assert diag.code == "SM026"
    assert diag.level == DiagnosticLevel.INFO
    assert "ix_users_user_email_lower" in diag.message
    assert "cannot verify" in diag.message
    assert "migrations-roundtrip-pg" in (diag.suggestion or "")


def test_postgres_and_unknown_dialect_are_silent():
    assert check_expression_indexes_unverifiable(_tables(), "postgresql", "users") == []
    assert check_expression_indexes_unverifiable(_tables(), None, "users") == []


def test_no_expression_indexes_is_silent():
    assert check_expression_indexes_unverifiable(_tables()[1:], "sqlite", "users") == []


def test_run_diagnostics_emits_sm026_for_installed_modules_on_sqlite():
    from simple_module_core.discovery import discover_modules

    modules = discover_modules()
    sqlite = [d for d in run_diagnostics(modules, database_dialect="sqlite") if d.code == "SM026"]
    postgres = [
        d for d in run_diagnostics(modules, database_dialect="postgresql") if d.code == "SM026"
    ]
    unset = [d for d in run_diagnostics(modules) if d.code == "SM026"]

    # The users module declares ix_users_user_email_lower.
    assert any("ix_users_user_email_lower" in d.message for d in sqlite)
    assert postgres == []
    assert unset == []


def test_module_without_models_is_skipped():
    from simple_module_core.diagnostics._expression_index import module_all_tables

    class NoModels(ModuleBase):
        meta = ModuleMeta(name="NoModels")

    assert module_all_tables(NoModels()) == []
