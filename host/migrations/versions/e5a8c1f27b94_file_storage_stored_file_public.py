"""file_storage_stored_file: add ``public`` flag

Opt-in anonymous serving (GH #353). Existing rows stay private.
``server_default=sa.false()`` renders ``0`` on SQLite and ``false`` on
Postgres, so the same migration runs on both.

Revision ID: e5a8c1f27b94
Revises: c7f2d9a41e83
Create Date: 2026-10-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a8c1f27b94"
down_revision: str | None = "c7f2d9a41e83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "file_storage_stored_file"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("public")
