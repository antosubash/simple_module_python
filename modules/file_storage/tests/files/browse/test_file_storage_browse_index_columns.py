"""The browse index is written with column constructs SQLite can reflect (GH #869)."""

import sqlalchemy as sa
from file_storage.models import StoredFile
from sqlalchemy.sql.elements import TextClause, UnaryExpression
from sqlalchemy.sql.operators import desc_op

_INDEX = "ix_file_storage_stored_file_tenant_browse"


def _browse_index() -> sa.Index:
    return next(i for i in StoredFile.__table__.indexes if i.name == _INDEX)


def test_browse_index_has_no_text_clause():
    assert not any(isinstance(e, TextClause) for e in _browse_index().expressions)


def test_browse_index_column_order():
    expressions = _browse_index().expressions
    names = []
    for expr in expressions:
        if isinstance(expr, UnaryExpression):
            assert expr.modifier is desc_op
            expr = expr.element
        # sa.desc("created_at") wraps a textual label reference, not a Column.
        names.append(getattr(expr, "name", None) or expr.element)
    assert names == ["tenant_id", "is_deleted", "created_at", "id"]
    assert isinstance(expressions[2], UnaryExpression)
