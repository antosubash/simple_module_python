"""add feature_flags override table

Revision ID: cf714c8bf117
Revises: 1fe7590fc594
Create Date: 2026-04-19 13:58:41.316854
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf714c8bf117"
down_revision: str | None = "1fe7590fc594"
branch_labels: str | Sequence[str] | None = ("feature_flags",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On PostgreSQL, create the `feature_flags` schema before creating tables.
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS feature_flags")

    op.create_table(
        "feature_flags_override",
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
        sa.Column("scope", sa.String(length=10), nullable=False, server_default="system"),
        sa.Column("scope_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_flags_override")),
        sa.UniqueConstraint(
            "scope",
            "scope_id",
            "name",
            name="uq_feature_flags_override_scope_scope_id_name",
        ),
    )
    op.create_index(
        op.f("ix_feature_flags_override_scope"),
        "feature_flags_override",
        ["scope"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_flags_override_scope_id"),
        "feature_flags_override",
        ["scope_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_feature_flags_override_name"),
        "feature_flags_override",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_feature_flags_override_name"),
        table_name="feature_flags_override",
    )
    op.drop_index(
        op.f("ix_feature_flags_override_scope_id"),
        table_name="feature_flags_override",
    )
    op.drop_index(
        op.f("ix_feature_flags_override_scope"),
        table_name="feature_flags_override",
    )
    op.drop_table("feature_flags_override")

    # On PostgreSQL, drop the `feature_flags` schema.
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP SCHEMA IF EXISTS feature_flags")
