"""Enforce case-insensitive login identities without changing accounts (#731).

Revision ID: e731a1b2c3d4
Revises: f5b1c3e8a207
"""

import sqlalchemy as sa
from alembic import op

revision = "e731a1b2c3d4"
down_revision = "f5b1c3e8a207"
branch_labels = None
depends_on = None

_TABLE = "users_user"
_INDEX = "ix_users_user_email_lower"


def upgrade() -> None:
    users = sa.table(_TABLE, sa.column("email"))
    email = users.c.email
    duplicates = (
        sa.select(sa.func.lower(email)).group_by(sa.func.lower(email)).having(sa.func.count() > 1)
    )
    conflicts = list(
        op.get_bind()
        .execute(sa.select(email).where(sa.func.lower(email).in_(duplicates)).order_by(email))
        .scalars()
    )
    if conflicts:
        raise RuntimeError(
            "Cannot enforce case-insensitive email uniqueness. Conflicting emails: "
            + ", ".join(conflicts)
            + ". Assign distinct emails and retry; no accounts were merged or deleted."
        )
    op.drop_index(_INDEX, table_name=_TABLE, if_exists=True)
    # Hand-written: SQLite autogenerate cannot reflect expression indexes.
    op.create_index(_INDEX, _TABLE, [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.create_index(_INDEX, _TABLE, [sa.text("lower(email)")])
