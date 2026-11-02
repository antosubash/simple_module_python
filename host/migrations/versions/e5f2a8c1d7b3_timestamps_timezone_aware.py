"""users_refresh_token / background_tasks_task_execution: timestamps -> timestamptz

SQLModel's ``datetime`` fields map to ``UTCDateTime`` (``DateTime(timezone=True)``),
but these columns were created by autogenerate on SQLite as naive ``DateTime()``.
SQLite cannot tell the difference; on PostgreSQL they are ``timestamp without
time zone`` and ``alembic check`` reports ``modify_type`` drift on each of them
(found by the PostgreSQL round-trip CI job, GH #342).

Existing values are UTC (the application always wrote UTC), so they are
reinterpreted ``AT TIME ZONE 'UTC'`` rather than shifted. A no-op on SQLite.


Revision ID: e5f2a8c1d7b3
Revises: c7f2d9a41e83
Create Date: 2026-10-05 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f2a8c1d7b3"
down_revision: str | None = "c7f2d9a41e83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("background_tasks_task_execution", "queued_at", True),
    ("background_tasks_task_execution", "started_at", True),
    ("background_tasks_task_execution", "finished_at", True),
    ("background_tasks_task_execution", "heartbeat_at", True),
    ("users_refresh_token", "created_at", False),
    ("users_refresh_token", "expires_at", False),
    ("users_refresh_token", "revoked_at", True),
)


def _retype(*, aware: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, nullable in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=aware),
            existing_type=sa.DateTime(timezone=not aware),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def upgrade() -> None:
    _retype(aware=True)


def downgrade() -> None:
    _retype(aware=False)
