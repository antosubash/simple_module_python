"""The host's initial OIDC migration creates the actual identity schema."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError


def _migration():
    path = Path("host/migrations/versions/c9d2e4f6a810_oidc_initial_schema.py")
    spec = spec_from_file_location("oidc_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_oidc_migration_roundtrip():
    revision = _migration()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        revision.upgrade()
        columns = {c["name"] for c in sa.inspect(conn).get_columns("oidc_user_cache")}
        assert columns == {"id", "issuer", "subject", "email", "full_name", "last_login_at"}
        conn.execute(
            sa.text(
                "INSERT INTO oidc_user_cache (id, issuer, subject, email) "
                "VALUES ('1', 'https://one', 'user', '')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO oidc_user_cache (id, issuer, subject, email) "
                "VALUES ('2', 'https://two', 'user', '')"
            )
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO oidc_user_cache (id, issuer, subject, email) "
                    "VALUES ('3', 'https://one', 'user', '')"
                )
            )
        revision.downgrade()
        assert not sa.inspect(conn).has_table("oidc_user_cache")
        revision.upgrade()


def test_oidc_postgres_ddl():
    from io import StringIO

    output = StringIO()
    with Operations.context(
        MigrationContext.configure(
            dialect=postgresql.dialect(), opts={"as_sql": True, "output_buffer": output}
        )
    ):
        _migration().upgrade()
    sql = output.getvalue()
    assert "UUID" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "UNIQUE (issuer, subject)" in sql
