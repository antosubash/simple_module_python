"""create file_storage tables

Revision ID: 5d44218ee368
Revises: b7e1af4c9d02
Create Date: 2026-04-19 11:20:24.247357
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d44218ee368"
down_revision: str | None = "b7e1af4c9d02"
branch_labels: str | Sequence[str] | None = ("file_storage",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS file_storage")

    op.create_table(
        "file_storage_stored_file",
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("backend", sa.String(length=32), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_storage_stored_file")),
    )
    op.create_index(
        "ix_file_storage_stored_file_created_by",
        "file_storage_stored_file",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_file_storage_stored_file_is_deleted",
        "file_storage_stored_file",
        ["is_deleted"],
        unique=False,
    )
    op.create_index(
        "ix_file_storage_stored_file_key",
        "file_storage_stored_file",
        ["key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_file_storage_stored_file_key", table_name="file_storage_stored_file")
    op.drop_index("ix_file_storage_stored_file_is_deleted", table_name="file_storage_stored_file")
    op.drop_index("ix_file_storage_stored_file_created_by", table_name="file_storage_stored_file")
    op.drop_table("file_storage_stored_file")

    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP SCHEMA IF EXISTS file_storage")
