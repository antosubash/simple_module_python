"""SQLAlchemy's and Alembic's SQLite expression-index warnings are quiet (GH #933).

The revision hook re-emits the models' expression indexes for new tables and
names the ones the database lacks, so the two library warnings about the same
index told a fresh app nothing it could act on, on every `make migration`.
"""

from __future__ import annotations

import warnings

import sqlalchemy as sa
from alembic.autogenerate import produce_migrations
from alembic.runtime.migration import MigrationContext
from simple_module_db.migrations import make_process_revision_directives, render_item


def _metadata() -> sa.MetaData:
    md = sa.MetaData()
    sa.Table(
        "people",
        md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String),
        sa.Index("ix_people_email_lower", sa.text("lower(email)"), unique=True),
    )
    return md


def _autogenerate_warnings(*, undeclared_index: bool = False) -> list[str]:
    target = _metadata()
    engine = sa.create_engine("sqlite://")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hook = make_process_revision_directives(target)
        with engine.connect() as conn:
            _metadata().create_all(conn)
            if undeclared_index:
                conn.execute(sa.text("CREATE INDEX ix_people_abs_id ON people (abs(id))"))
            ctx = MigrationContext.configure(conn, opts={"render_item": render_item})
            hook(ctx, None, [produce_migrations(ctx, target)])
    return [str(w.message) for w in caught]


def test_declared_expression_indexes_raise_no_library_warnings() -> None:
    assert not [m for m in _autogenerate_warnings() if "ix_people_email_lower" in m]


def test_an_index_the_models_do_not_declare_still_warns() -> None:
    messages = _autogenerate_warnings(undeclared_index=True)
    assert any("ix_people_abs_id" in m for m in messages)
