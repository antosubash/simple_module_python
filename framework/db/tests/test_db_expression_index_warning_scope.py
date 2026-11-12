"""The SQLite expression-index warning names only what the revision missed (GH #917).

The hook used to warn about every expression index in the metadata, before it
had re-emitted them, so a fresh app's initial schema (which does create the
index) and every unrelated module migration told users to hand-edit it in.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic.autogenerate import produce_migrations
from alembic.runtime.migration import MigrationContext
from simple_module_core.diagnostics._expression_index import expression_index_advice
from simple_module_db.migrations import make_process_revision_directives, render_item


def _metadata(*, extra_column: bool = False) -> sa.MetaData:
    md = sa.MetaData()
    sa.Table(
        "people",
        md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String),
        *([sa.Column("nickname", sa.String)] if extra_column else []),
        sa.Index("ix_people_email_lower", sa.text("lower(email)"), unique=True),
    )
    sa.Table("orders", md, sa.Column("id", sa.Integer, primary_key=True))
    return md


def _run_hook(existing: sa.MetaData | None, target: sa.MetaData, caplog) -> str:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        if existing is not None:
            existing.create_all(conn)
        ctx = MigrationContext.configure(conn, opts={"render_item": render_item})
        script = produce_migrations(ctx, target)
        with caplog.at_level(logging.WARNING, logger="alembic.env"):
            make_process_revision_directives(target)(ctx, None, [script])
    return caplog.text


def test_initial_schema_that_creates_the_index_is_silent(caplog) -> None:
    assert "ix_people_email_lower" not in _run_hook(None, _metadata(), caplog)


def test_revision_on_another_table_is_silent(caplog) -> None:
    existing = _metadata()
    existing.remove(existing.tables["orders"])
    assert "ix_people_email_lower" not in _run_hook(existing, _metadata(), caplog)


def test_revision_altering_a_table_whose_index_exists_is_silent(caplog) -> None:
    """SQLite records the index's name even though it cannot reflect it."""
    text = _run_hook(_metadata(), _metadata(extra_column=True), caplog)
    assert "ix_people_email_lower" not in text


def test_an_expression_index_added_to_an_existing_table_warns(caplog) -> None:
    """Autogenerate emits nothing for it on SQLite, so the revision misses it."""
    existing = _metadata()
    existing.tables["people"].indexes.clear()
    text = _run_hook(existing, _metadata(), caplog)
    assert "ix_people_email_lower on people" in text


def test_advice_outside_this_repo_points_at_what_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    advice = expression_index_advice()
    assert "migrations-roundtrip-pg" not in advice
    assert "alembic -c host/alembic.ini check" in advice
    assert "PostgreSQL" in advice


def test_advice_in_a_checkout_with_the_roundtrip_target(tmp_path, monkeypatch) -> None:
    (tmp_path / "Makefile").write_text("migrations-roundtrip-pg:\n\techo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert "make migrations-roundtrip-pg" in expression_index_advice()


def test_a_ci_prefixed_target_is_not_the_roundtrip_target(tmp_path, monkeypatch) -> None:
    (tmp_path / "Makefile").write_text("ci-migrations-roundtrip-pg:\n\techo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert "make migrations-roundtrip-pg" not in expression_index_advice()
