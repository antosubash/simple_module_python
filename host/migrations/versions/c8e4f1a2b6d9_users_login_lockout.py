"""users login lockout columns

Revision ID: c8e4f1a2b6d9
Revises: b5018b617142
Create Date: 2026-10-19 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e4f1a2b6d9"
down_revision: str | None = "b5018b617142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Login lockout moves from per-worker memory to the user row (GH #530), so it
# holds across workers, source IPs and restarts. Every existing account starts
# unlocked with a zero count; nothing to backfill.


def upgrade() -> None:
    op.add_column(
        "users_user",
        sa.Column(
            "failed_login_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "users_user",
        sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users_user",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users_user", "locked_until")
    op.drop_column("users_user", "last_failed_login_at")
    op.drop_column("users_user", "failed_login_count")
