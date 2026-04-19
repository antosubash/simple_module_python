"""add permissions user permission table

Revision ID: 9557a7c2e646
Revises: 5d08d8587674
Create Date: 2026-04-19 09:43:57.944179
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

# revision identifiers, used by Alembic.
revision: str = "9557a7c2e646"
down_revision: str | None = "5d08d8587674"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "permissions_user_permission",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("permission_key", sa.String(length=128), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint(
            "user_id",
            "permission_key",
            name=op.f("pk_permissions_user_permission"),
        ),
    )
    op.create_index(
        "ix_permissions_user_permission_key",
        "permissions_user_permission",
        ["permission_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_permissions_user_permission_key",
        table_name="permissions_user_permission",
    )
    op.drop_table("permissions_user_permission")
