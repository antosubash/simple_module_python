"""file_storage: resumable upload sessions, nullable checksum (#454)

Multipart uploads bypass the app, so nothing hashes them on the way in: the
checksum becomes nullable and is filled in later by a background task. The
downgrade backfills nulls with an empty string before restoring NOT NULL.

Revision ID: a659221c464b
Revises: e5a8c1f27b94
Create Date: 2026-10-15 10:18:19.289035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a659221c464b"
down_revision: str | None = "e5a8c1f27b94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_storage_upload_session",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
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
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column("part_size", sa.BigInteger(), nullable=False),
        sa.Column("backend_upload_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_storage_upload_session")),
    )
    op.create_index(
        "ix_file_storage_upload_session_created_by",
        "file_storage_upload_session",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        "ix_file_storage_upload_session_status_expires",
        "file_storage_upload_session",
        ["status", "expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_file_storage_upload_session_tenant_id"),
        "file_storage_upload_session",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_file_storage_upload_session_tenant_key",
        "file_storage_upload_session",
        ["tenant_id", "key"],
        unique=True,
    )
    with op.batch_alter_table("file_storage_stored_file") as batch:
        batch.alter_column("checksum_sha256", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    op.execute(
        "UPDATE file_storage_stored_file SET checksum_sha256 = '' WHERE checksum_sha256 IS NULL"
    )
    with op.batch_alter_table("file_storage_stored_file") as batch:
        batch.alter_column("checksum_sha256", existing_type=sa.String(length=64), nullable=False)
    op.drop_index(
        "ix_file_storage_upload_session_tenant_key", table_name="file_storage_upload_session"
    )
    op.drop_index(
        op.f("ix_file_storage_upload_session_tenant_id"), table_name="file_storage_upload_session"
    )
    op.drop_index(
        "ix_file_storage_upload_session_status_expires", table_name="file_storage_upload_session"
    )
    op.drop_index(
        "ix_file_storage_upload_session_created_by", table_name="file_storage_upload_session"
    )
    op.drop_table("file_storage_upload_session")
