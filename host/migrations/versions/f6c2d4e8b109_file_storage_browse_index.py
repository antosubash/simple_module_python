"""Index tenant file browsing in page order.

Revision ID: f6c2d4e8b109
Revises: e731a1b2c3d4 (current file_storage@head on the shared trunk)
"""

import sqlalchemy as sa
from alembic import op

revision = "f6c2d4e8b109"
down_revision = "e731a1b2c3d4"
branch_labels = None
depends_on = None

_TABLE = "file_storage_stored_file"
_INDEX = "ix_file_storage_stored_file_tenant_browse"


def upgrade() -> None:
    op.create_index(_INDEX, _TABLE, ["tenant_id", "is_deleted", sa.text("created_at DESC"), "id"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
