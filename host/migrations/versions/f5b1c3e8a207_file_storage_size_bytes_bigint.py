"""file_storage_stored_file.size_bytes: BIGINT (#708)

``size_bytes`` was a 32-bit ``INTEGER`` on Postgres, so storing a file of
2 GiB or more failed on insert. Server-side puts now go multipart above
5 GiB (#708), so the column must hold any object size. SQLite's INTEGER is
already 64-bit; the batch alter is a no-op rebuild there.

file_storage had no label of its own (its table came in with the initial
schema); this revision gives it one.

Revision ID: f5b1c3e8a207
Revises: b31a70971001
Create Date: 2026-10-30 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5b1c3e8a207"
down_revision: str | None = "b31a70971001"
branch_labels: str | Sequence[str] | None = ("file_storage",)
depends_on: str | Sequence[str] | None = None

_TABLE = "file_storage_stored_file"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "size_bytes", existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False
        )


def downgrade() -> None:
    # Fails on Postgres if a stored file is 2 GiB or larger; that is the point.
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column(
            "size_bytes", existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False
        )
