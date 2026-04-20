"""Structure tests for the users.User SQLAlchemy model."""

from __future__ import annotations

from sqlalchemy import inspect


def column_names(table) -> set[str]:
    """Return the set of column names for a mapped class's table."""
    return {c.key for c in inspect(table).mapper.column_attrs}


class TestUserTableShape:
    def test_tablename(self):
        from users.models import User

        assert User.__tablename__ == "users_user"

    def test_last_login_at_is_indexed(self):
        from users.models import User

        assert any(
            "last_login_at" in {c.name for c in i.columns} for i in User.__table__.indexes
        ), "User.last_login_at must be indexed"

    def test_required_columns(self):
        from users.models import User

        cols = column_names(User)
        expected = {
            "id",
            "email",
            "hashed_password",
            "is_active",
            "is_superuser",
            "is_verified",
            "full_name",
            "tenant_id",
            "disabled_at",
            "last_login_at",
            # AuditMixin columns
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert expected <= cols, f"Missing columns: {expected - cols}"
