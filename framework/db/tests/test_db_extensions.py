"""Postgres extensions + LTree/TSVector fallbacks, on SQLite (GH #458)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_db import LTree, TSVector, UnsupportedDatabaseError, ensure_db_extensions
from simple_module_db.migrations import render_item
from sqlalchemy.dialects import postgresql, sqlite


def _module(name: str, *extensions: str) -> ModuleBase:
    class _M(ModuleBase):
        meta = ModuleMeta(name=name)

        def db_extensions(self) -> list[str]:
            return list(extensions)

    return _M()


def test_no_extensions_is_a_noop_even_on_sqlite():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        assert ensure_db_extensions(conn, [_module("a")]) == []


def test_sqlite_raises_naming_module_and_extensions():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn, pytest.raises(UnsupportedDatabaseError) as exc:
        ensure_db_extensions(conn, [_module("taxonomy", "ltree")])
    assert "taxonomy" in str(exc.value)
    assert "ltree" in str(exc.value)


@pytest.mark.parametrize("bad", ["LTree", "X", "1abc", 'x"; DROP', 'bad"name', "x;drop", "-a", ""])
def test_invalid_extension_name_is_rejected(bad: str):
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn, pytest.raises(ValueError, match="invalid database extension"):
        ensure_db_extensions(conn, [_module("m", bad)])


def test_hyphenated_extension_name_is_accepted_and_quoted(monkeypatch):
    from alembic import context
    from simple_module_db.extensions import declared_extensions

    assert declared_extensions([_module("m", "uuid-ossp")]) == {"uuid-ossp": ["m"]}

    emitted: list[str] = []

    class _Ctx:
        dialect = type("D", (), {"name": "postgresql"})()

    monkeypatch.setattr(context, "get_context", lambda: _Ctx())
    monkeypatch.setattr(context, "execute", emitted.append)
    ensure_db_extensions(None, [_module("m", "uuid-ossp")])
    assert emitted == ['CREATE EXTENSION IF NOT EXISTS "uuid-ossp"']


def test_types_are_text_on_sqlite_and_native_on_postgres():
    md = sa.MetaData()
    t = sa.Table(
        "dbext_t",
        md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("path", LTree()),
        sa.Column("doc", TSVector()),
    )
    sqlite_ddl = str(sa.schema.CreateTable(t).compile(dialect=sqlite.dialect()))
    pg_ddl = str(sa.schema.CreateTable(t).compile(dialect=postgresql.dialect()))
    assert "path TEXT" in sqlite_ddl and "doc TEXT" in sqlite_ddl
    assert "path LTREE" in pg_ddl and "doc TSVECTOR" in pg_ddl


def test_types_round_trip_strings_on_sqlite():
    md = sa.MetaData()
    t = sa.Table("dbext_t", md, sa.Column("path", LTree()), sa.Column("doc", TSVector()))
    engine = sa.create_engine("sqlite://")
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(t.insert().values(path="top.science", doc="'a':1"))
        assert conn.execute(sa.select(t.c.path, t.c.doc)).one() == ("top.science", "'a':1")


@pytest.mark.parametrize(("type_", "name"), [(LTree(), "LTree"), (TSVector(), "TSVector")])
def test_render_item_emits_runnable_code_with_import(type_, name: str):
    class _Ctx:
        imports: set[str] = set()  # noqa: RUF012

    ctx = _Ctx()
    ctx.imports = set()
    assert render_item("type", type_, ctx) == f"simple_module_db.types.{name}()"
    assert "import simple_module_db.types" in ctx.imports
