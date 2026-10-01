"""users_user: drop the legacy tenant_id column

Tenant membership lives in ``tenants_membership`` and the active tenant is
resolved per request, so the copy on the user row was dead weight that could
only go stale. ``User`` stays platform-global. See GH #381.

Revision ID: d4e8a1b6c392
Revises: c3a1d7e45f20
Create Date: 2026-10-01 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e8a1b6c392"
down_revision: str | None = "c3a1d7e45f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_users_user_tenant_id"


def upgrade() -> None:
    # batch mode: SQLite cannot drop an indexed column in place.
    with op.batch_alter_table("users_user") as batch:
        batch.drop_index(_INDEX)
        batch.drop_column("tenant_id")


def downgrade() -> None:
    with op.batch_alter_table("users_user") as batch:
        batch.add_column(sa.Column("tenant_id", sa.String(length=50), nullable=True))
        batch.create_index(_INDEX, ["tenant_id"], unique=False)
