"""users_refresh_token.user_id: Uuid -> GUID, to match users_user.id

``User.id`` uses fastapi-users' ``GUID`` type; ``RefreshToken.user_id`` was
left on SQLModel's default ``Uuid``. The two are identical on Postgres (both
render ``UUID``) but not on SQLite, where ``Uuid`` stores the bare 32-char hex
and ``GUID`` the 36-char dashed form. The foreign key therefore never matched a
parent row on SQLite, and any SQL join across it returned nothing — silently,
because SQLite ships with FK enforcement off. See GH #339.

So this migration is a no-op on Postgres and a data rewrite on SQLite.

Revision ID: c3a1d7e45f20
Revises: b4c1e7d9a025
Create Date: 2026-09-21 15:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

# revision identifiers, used by Alembic.
revision: str = "c3a1d7e45f20"
down_revision: str | None = "b4c1e7d9a025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "users_refresh_token"

# 32-char hex -> 8-4-4-4-12 dashed form, in SQLite's string functions.
_TO_DASHED = (
    "substr(user_id, 1, 8) || '-' || substr(user_id, 9, 4) || '-' || "
    "substr(user_id, 13, 4) || '-' || substr(user_id, 17, 4) || '-' || substr(user_id, 21, 12)"
)
_TO_HEX = "replace(user_id, '-', '')"


def _rewrite(expression: str, where: str) -> None:
    op.execute(f"UPDATE {_TABLE} SET user_id = {expression} WHERE {where}")


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        # Postgres already stores both sides as native UUID; an ALTER here
        # would take a table lock to change nothing.
        return

    _rewrite(_TO_DASHED, "length(user_id) = 32")
    # Tokens whose user is gone could not authenticate anyway, and would block
    # the FK-checked table rebuild below.
    op.execute(f"DELETE FROM {_TABLE} WHERE user_id NOT IN (SELECT id FROM users_user)")
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.alter_column("user_id", type_=GUID(), existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return

    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.alter_column("user_id", type_=sa.Uuid(), existing_type=GUID(), nullable=False)
    _rewrite(_TO_HEX, "length(user_id) = 36")
