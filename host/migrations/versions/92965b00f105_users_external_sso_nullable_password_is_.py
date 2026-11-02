"""users external sso: nullable password + is_external

Revision ID: 92965b00f105
Revises: 873ca2015033
Create Date: 2026-06-23 16:08:20.901942
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92965b00f105"
down_revision: str | None = "873ca2015033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# External (SSO) users have no local password, so ``hashed_password`` becomes
# nullable and a marker column ``is_external`` is added. SQLite cannot ALTER a
# column's nullability in place, so the change goes through ``batch_alter_table``
# (a table rebuild on SQLite, a direct ALTER on Postgres). The rebuild can't
# reflect the expression-based ``lower(email)`` index, so it's dropped and
# recreated explicitly on SQLite.


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("users_user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_external",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=1024),
            nullable=True,
        )
    if bind.dialect.name == "sqlite":
        op.execute("DROP INDEX IF EXISTS ix_users_user_email_lower")
        op.create_index("ix_users_user_email_lower", "users_user", [sa.text("lower(email)")])


def downgrade() -> None:
    # Restoring ``hashed_password NOT NULL`` will fail if any external (SSO)
    # user exists at downgrade time — they carry a NULL password by design.
    # Such rows must be deleted or given a password before downgrading.
    bind = op.get_bind()
    with op.batch_alter_table("users_user") as batch_op:
        batch_op.alter_column(
            "hashed_password",
            existing_type=sa.String(length=1024),
            nullable=False,
        )
        batch_op.drop_column("is_external")
    if bind.dialect.name == "sqlite":
        op.execute("DROP INDEX IF EXISTS ix_users_user_email_lower")
        op.create_index("ix_users_user_email_lower", "users_user", [sa.text("lower(email)")])
