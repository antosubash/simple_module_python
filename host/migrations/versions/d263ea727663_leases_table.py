"""leases table (GH #539)

Framework-owned ``sm_lease`` for the database lease backend. Its own root and
``leases`` label: it depends on no module's tables.

Revision ID: d263ea727663
Revises:
Create Date: 2026-10-21 18:07:40.451232
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d263ea727663"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("leases",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sm_lease",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("holder", sa.String(length=255), nullable=False),
        sa.Column("fence", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", "slot", name=op.f("pk_sm_lease")),
    )


def downgrade() -> None:
    op.drop_table("sm_lease")
