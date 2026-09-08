"""users_access_token per-row expires_at and session_version

Revision ID: b4c1e7d9a025
Revises: f53464f5ac43
Create Date: 2026-09-04 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c1e7d9a025"
down_revision: str | None = "f53464f5ac43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``expires_at`` moves the token deadline from one process-wide constant onto
# each row. The rows do not all mean the same thing — ``/auth/token`` promises
# fifteen minutes, an ordinary sign-in writes a fourteen-day cookie, "keep me
# signed in" asks for thirty days — and reading all three back against a single
# thirty-day window meant a cookie lifted off disk stayed replayable for a
# month whatever it had been issued for.
#
# ``session_version`` is the bearer half of "sign out everywhere": stamped at
# mint time, compared against the account's counter on every read, so a password
# change strands tokens the way it already stranded sessions.
#
# Both are backfilled with the values the existing rows were actually minted
# under — thirty days from ``created_at``, and the owning account's current
# counter — so upgrading signs nobody out and leaves no NULL branch behind for
# the read path to fail open on.

_THIRTY_DAYS = "30 days"


def upgrade() -> None:
    op.add_column(
        "users_access_token",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users_access_token",
        sa.Column(
            "session_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        deadline = f"created_at + INTERVAL '{_THIRTY_DAYS}'"
    else:
        deadline = "datetime(created_at, '+30 days')"
    op.execute(f"UPDATE users_access_token SET expires_at = {deadline}")
    op.execute(
        "UPDATE users_access_token SET session_version = COALESCE("
        "(SELECT session_version FROM users_user WHERE users_user.id = users_access_token.user_id)"
        ", 0)"
    )

    with op.batch_alter_table("users_access_token") as batch:
        batch.alter_column("expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_index(
        "ix_users_access_token_expires_at", "users_access_token", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_users_access_token_expires_at", table_name="users_access_token")
    op.drop_column("users_access_token", "session_version")
    op.drop_column("users_access_token", "expires_at")
