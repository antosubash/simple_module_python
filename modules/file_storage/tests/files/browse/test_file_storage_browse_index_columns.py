"""The browse index is written with column constructs SQLite can reflect (GH #869).

``sa.text("created_at DESC")`` and ``sa.desc("created_at")`` are both expressions
to Alembic, and SQLite reflects the index as plain columns, so every SQLite
autogenerate reported the index as changed. ``sa.desc(sa.column(...))`` compares
as a column.
"""

import sqlalchemy as sa
from file_storage.models import StoredFile
from sqlalchemy.sql.elements import ColumnClause, UnaryExpression
from sqlalchemy.sql.operators import desc_op

_INDEX = "ix_file_storage_stored_file_tenant_browse"


def _browse_index() -> sa.Index:
    return next(i for i in StoredFile.__table__.indexes if i.name == _INDEX)


def test_every_element_is_a_column_or_a_descending_column():
    names = []
    for expr in _browse_index().expressions:
        if isinstance(expr, UnaryExpression):
            assert expr.modifier is desc_op
            expr = expr.element
        assert isinstance(expr, ColumnClause), f"{expr!r} is an expression to Alembic"
        names.append(expr.name)
    assert names == ["tenant_id", "is_deleted", "created_at", "id"]
    assert isinstance(_browse_index().expressions[2], UnaryExpression)


def test_the_ddl_is_unchanged():
    """Same ``CREATE INDEX`` as revision ``f6c2d4e8b109``, so no migration is needed."""
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex

    for dialect in (sqlite.dialect(), postgresql.dialect()):
        ddl = str(CreateIndex(_browse_index()).compile(dialect=dialect))
        assert ddl.endswith("(tenant_id, is_deleted, created_at DESC, id)"), ddl
