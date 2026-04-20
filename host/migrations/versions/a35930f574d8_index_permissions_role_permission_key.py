"""index permissions role permission key

Revision ID: a35930f574d8
Revises: 9557a7c2e646
Create Date: 2026-04-19 11:52:35.013862
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a35930f574d8"
down_revision: str | None = "9557a7c2e646"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_permissions_role_permission_key",
        "permissions_role_permission",
        ["permission_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_permissions_role_permission_key",
        table_name="permissions_role_permission",
    )
