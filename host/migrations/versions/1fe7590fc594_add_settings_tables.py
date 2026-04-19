"""add settings tables

Revision ID: 1fe7590fc594
Revises: b7e1af4c9d02
Create Date: 2026-04-19 07:46:59.090748
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1fe7590fc594"
down_revision: str | None = "b7e1af4c9d02"
branch_labels: str | Sequence[str] | None = ("settings",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On PostgreSQL, create the `settings` schema before creating tables.
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS settings")

    op.create_table(
        "settings_setting",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("value", sa.String(length=4000), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_settings_setting")),
    )
    op.create_index(
        op.f("ix_settings_setting_key"),
        "settings_setting",
        ["key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_settings_setting_key"), table_name="settings_setting")
    op.drop_table("settings_setting")

    # On PostgreSQL, drop the `settings` schema.
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP SCHEMA IF EXISTS settings")
