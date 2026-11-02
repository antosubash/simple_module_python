"""keycloak_user_cache.last_login_at: timestamp -> timestamptz

Same drift as ``e5f2a8c1d7b3`` (naive ``DateTime()`` created on SQLite, model
declares a timezone-aware column), on the keycloak branch. Values are UTC and
are reinterpreted ``AT TIME ZONE 'UTC'``. A no-op on SQLite.

Revision ID: f6a3b9d2e8c4
Revises: 168a2882f443
Create Date: 2026-10-05 10:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a3b9d2e8c4"
down_revision: str | None = "168a2882f443"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _retype(*, aware: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.alter_column(
        "keycloak_user_cache",
        "last_login_at",
        type_=sa.DateTime(timezone=aware),
        existing_type=sa.DateTime(timezone=not aware),
        existing_nullable=True,
        postgresql_using="last_login_at AT TIME ZONE 'UTC'",
    )


def upgrade() -> None:
    _retype(aware=True)


def downgrade() -> None:
    _retype(aware=False)
