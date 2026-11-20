"""users: unbounded OAuth access and refresh tokens (#1054).

Revision ID: a1054e9c7b62
Revises: f999a1b2c3d4 (users@head on the shared trunk)
"""

import sqlalchemy as sa
from alembic import op

revision = "a1054e9c7b62"
down_revision = "f999a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users_oauth_account") as batch:
        batch.alter_column(
            "access_token",
            type_=sa.Text(),
            existing_type=sa.String(length=1024),
            existing_nullable=False,
        )
        batch.alter_column(
            "refresh_token",
            type_=sa.Text(),
            existing_type=sa.String(length=1024),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("users_oauth_account") as batch:
        batch.alter_column(
            "access_token",
            type_=sa.String(length=1024),
            existing_type=sa.Text(),
            existing_nullable=False,
        )
        batch.alter_column(
            "refresh_token",
            type_=sa.String(length=1024),
            existing_type=sa.Text(),
            existing_nullable=True,
        )
