"""Structure tests for the users.Role SQLAlchemy model."""

from __future__ import annotations

from sqlalchemy import inspect


def column_names(table) -> set[str]:
    """Return the set of column names for a mapped class's table."""
    return {c.key for c in inspect(table).mapper.column_attrs}


class TestRoleTableShape:
    def test_tablename(self):
        from users.models import Role

        assert Role.__tablename__ == "users_role"

    def test_required_columns(self):
        from users.models import Role

        cols = column_names(Role)
        expected = {
            "id",
            "name",
            "description",
            # AuditMixin columns
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= cols, f"Missing columns: {expected - cols}"
