"""Shared sealed browser refresh outcomes (#738).

Revision ID: a738c2e4f601
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "a738c2e4f601"
down_revision = None
branch_labels = ("auth",)
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_refresh_outcome",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("session", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_auth_refresh_outcome")),
    )
    op.create_index("ix_auth_refresh_outcome_expires_at", "auth_refresh_outcome", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_refresh_outcome_expires_at", table_name="auth_refresh_outcome")
    op.drop_table("auth_refresh_outcome")
