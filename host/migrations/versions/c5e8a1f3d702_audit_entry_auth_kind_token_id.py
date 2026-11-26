"""audit_log_audit_entry: add nullable auth_kind and token_id

Records how the actor authenticated (``session``, ``pat``, ``service``, ...)
and, for a token, the credential id. NULL on rows written before this
revision. See GH #1178.

Revision ID: c5e8a1f3d702
Revises: 819d8c5714a5
Create Date: 2026-11-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e8a1f3d702"
down_revision: str | None = "819d8c5714a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "audit_log_audit_entry"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("auth_kind", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("token_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("token_id")
        batch.drop_column("auth_kind")
