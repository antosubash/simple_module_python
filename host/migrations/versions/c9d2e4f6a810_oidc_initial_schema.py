"""Initial issuer-scoped OIDC identity cache (#192).

Revision ID: c9d2e4f6a810
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d2e4f6a810"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("oidc",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_user_cache",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issuer", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_oidc_user_cache"),
        sa.UniqueConstraint("issuer", "subject", name="uq_oidc_user_cache_issuer_subject"),
    )


def downgrade() -> None:
    op.drop_table("oidc_user_cache")
