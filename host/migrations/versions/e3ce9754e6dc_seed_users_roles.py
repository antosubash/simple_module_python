"""seed users roles

Revision ID: e3ce9754e6dc
Revises: 8c12be982a27
Create Date: 2026-04-15 18:10:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3ce9754e6dc"
down_revision: str | None = "8c12be982a27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Duplicated from modules/users/users/constants.py — migrations are run from a
# context where module imports may not resolve (alembic discovers them via
# the simple_module entry point), and tying the migration to the module's
# import path is more fragile than hardcoding the stable UUIDs.
ADMIN_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ROLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def upgrade() -> None:
    roles_table = sa.table(
        "users_role",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    op.bulk_insert(
        roles_table,
        [
            {"id": ADMIN_ROLE_ID, "name": "admin", "description": "Administrator"},
            {"id": USER_ROLE_ID, "name": "user", "description": "Standard user"},
        ],
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM users_role WHERE id IN ('{ADMIN_ROLE_ID}', '{USER_ROLE_ID}')"
    )
