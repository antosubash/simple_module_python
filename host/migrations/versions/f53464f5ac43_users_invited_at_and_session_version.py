"""users invited_at and session_version

Revision ID: f53464f5ac43
Revises: 92965b00f105
Create Date: 2026-09-03 06:57:38.214115
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f53464f5ac43"
down_revision: str | None = "92965b00f105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``invited_at`` separates an admin-created invitation from a self-signup: both
# are ``is_active and not is_verified`` rows, and only the first has an
# outstanding email worth resending. Left NULL for every existing account —
# backfilling it from ``created_at`` would invent invitations nobody sent.
#
# ``session_version`` backs "sign out everywhere". Browser auth is a signed
# cookie, so revocation is a value every session carries and the auth provider
# compares. It defaults to 0 both in the column and in a session that predates
# this migration, so upgrading does not sign anybody out.


def upgrade() -> None:
    op.add_column(
        "users_user",
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users_user",
        sa.Column(
            "session_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users_user", "session_version")
    op.drop_column("users_user", "invited_at")
