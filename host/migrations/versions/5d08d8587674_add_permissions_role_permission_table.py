"""add permissions role permission table

Revision ID: 5d08d8587674
Revises: b7e1af4c9d02
Create Date: 2026-04-19 07:58:55.443793
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d08d8587674"
down_revision: str | None = "b7e1af4c9d02"
branch_labels: str | Sequence[str] | None = ("permissions",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On PostgreSQL, create the `permissions` schema before creating tables.
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS permissions")

    op.create_table(
        "permissions_role_permission",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("role_name", sa.String(length=64), nullable=False),
        sa.Column("permission_key", sa.String(length=128), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint(
            "role_name",
            "permission_key",
            name=op.f("pk_permissions_role_permission"),
        ),
    )


def downgrade() -> None:
    op.drop_table("permissions_role_permission")

    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP SCHEMA IF EXISTS permissions")
