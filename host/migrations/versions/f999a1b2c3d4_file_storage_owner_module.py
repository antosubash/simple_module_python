"""file_storage: per-module file access policies (#999).

Revision ID: f999a1b2c3d4
Revises: e480d7dd348f (file_storage@head on the shared trunk)
"""

import sqlalchemy as sa
from alembic import op

revision = "f999a1b2c3d4"
down_revision = "e480d7dd348f"
branch_labels = None
depends_on = None

_TABLE = "file_storage_stored_file"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("owner_module", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("owner_module")
