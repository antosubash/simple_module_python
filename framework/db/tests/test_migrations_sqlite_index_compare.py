"""SQLite loses text index ordering on reflection, but real changes must survive (GH #869)."""

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import context
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from simple_module_db.migrations import make_include_object
from sqlalchemy.dialects import postgresql

pytestmark = [
    pytest.mark.filterwarnings("ignore:Skipped unsupported reflection.*:sqlalchemy.exc.SAWarning"),
    pytest.mark.filterwarnings("ignore:autogenerate skipping metadata-specified.*:UserWarning"),
]


def _metadata(element="created_at DESC", *, first="tenant_id", unique=False):
    """``element`` is text for ``sa.text()``, or an already-built SQL element."""
    meta = sa.MetaData()
    sa.Table(
        "record",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer),
        sa.Column("created_at", sa.Integer),
        sa.Column("email", sa.String),
        sa.Index(
            "ix",
            first,
            sa.text(element) if isinstance(element, str) else element,
            "id",
            unique=unique,
        ),
    )
    return meta


def _index(meta):
    return next(iter(meta.tables["record"].indexes))


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def _environment(connection, meta, *, filtered=True):
    config = Config()
    config.set_main_option("script_location", "host/migrations")
    env = EnvironmentContext(config, None)
    options = {"include_object": make_include_object(meta)} if filtered else {}
    env.configure(connection=connection, target_metadata=meta, **options)
    return env


@pytest.mark.parametrize(
    "element", ["created_at DESC", '"created_at" ASC', "created_at", "Created_At DESC"]
)
def test_sqlite_text_index_compares_clean(connection, element):
    meta = _metadata(element)
    meta.create_all(connection)
    with _environment(connection, meta) as env:
        assert compare_metadata(env.get_context(), meta) == []


@pytest.mark.parametrize(
    "build",
    [lambda: sa.desc("created_at"), lambda: sa.desc(sa.column("created_at"))],
    ids=["label", "column"],
)
def test_sqlite_desc_index_compares_clean(connection, build):
    """``sa.desc("col")`` is a label expression; ``sa.desc(sa.column("col"))`` a column."""
    meta = _metadata(build())
    meta.create_all(connection)
    with _environment(connection, meta) as env:
        assert compare_metadata(env.get_context(), meta) == []


def test_sqlite_text_index_without_filter_reproduces_remove_add(connection):
    meta = _metadata()
    meta.create_all(connection)
    with _environment(connection, meta, filtered=False) as env:
        diffs = compare_metadata(env.get_context(), meta)
    assert [diff[0] for diff in diffs] == ["remove_index", "add_index"]


@pytest.mark.parametrize(
    "changes",
    [{"first": "email"}, {"unique": True}, {"element": "tenant_id DESC", "first": "created_at"}],
    ids=["different-column", "unique", "column-order"],
)
def test_sqlite_text_index_real_changes_are_reported(connection, changes):
    _metadata().create_all(connection)
    target = _metadata(**changes)
    with _environment(connection, target) as env:
        diffs = compare_metadata(env.get_context(), target)
    assert [diff[0] for diff in diffs] == ["remove_index", "add_index"]


@pytest.mark.parametrize("reflected", [False, True])
@pytest.mark.parametrize(
    "element",
    [
        "created_at",
        '"created_at"',
        "created_at asc",
        '"created_at" DESC NULLS LAST',
        "created_at NULLS FIRST",
    ],
)
def test_sqlite_text_index_filter_handles_both_comparison_directions(
    connection, reflected, element
):
    meta = _metadata(element)
    modeled = _index(meta)
    other = sa.MetaData()
    table = meta.tables["record"].to_metadata(other)
    table.indexes.clear()
    database = sa.Index("ix", table.c.tenant_id, table.c.created_at, table.c.id)
    obj, compare_to = (database, modeled) if reflected else (modeled, database)
    with _environment(connection, meta):
        assert make_include_object(meta)(obj, "ix", "index", reflected, compare_to) is False


@pytest.mark.parametrize("reflected", [False, True])
def test_sqlite_real_expression_is_not_hidden(connection, reflected):
    meta = _metadata("lower(email)")
    meta.create_all(connection)
    # SQLite cannot reflect this index, so exercise the callback pair directly.
    modeled = _index(meta)
    database = _index(_metadata("email"))
    obj, compare_to = (database, modeled) if reflected else (modeled, database)
    with _environment(connection, meta):
        assert make_include_object(meta)(obj, "ix", "index", reflected, compare_to) is True


def test_sqlite_text_index_without_active_context_is_not_hidden():
    meta = _metadata()
    assert (
        make_include_object(meta)(
            _index(meta), "ix", "index", False, _index(_metadata("created_at"))
        )
        is True
    )


def test_postgres_text_index_is_not_hidden(monkeypatch):
    """Postgres reflects the ordering, so its comparison is left to Alembic."""
    meta = _metadata()
    monkeypatch.setattr(
        context, "get_context", lambda: SimpleNamespace(dialect=postgresql.dialect())
    )
    assert (
        make_include_object(meta)(
            _index(meta), "ix", "index", False, _index(_metadata("created_at"))
        )
        is True
    )
