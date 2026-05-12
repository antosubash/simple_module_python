"""users_user lower(email) functional index

Revision ID: 41cf2c53660e
Revises: 3bf3f9db7f7f
Create Date: 2026-05-12 00:00:00.000000

The functional index ``ix_users_user_email_lower`` on ``lower(users_user.email)``
backs the case-insensitive lookup used by ``UserDatabaseWithRoles.get_by_email``
and ``users.bootstrap``. Autogenerate silently dropped it from the original
initial-schema revision (``77162e7b184b``) because SQLAlchemy 2.0 can't reflect
expression-based indexes under the SQLite dialect, so dev DBs are missing it.
This revision back-fills the index unconditionally.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "41cf2c53660e"
down_revision: str | None = "3bf3f9db7f7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``if_not_exists`` covers the case where a Postgres developer's original
    # autogen run already emitted this index (only SQLite skips it).
    op.create_index(
        "ix_users_user_email_lower",
        "users_user",
        [sa.text("lower(email)")],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_user_email_lower", table_name="users_user", if_exists=True)
