"""Frozen token-storage upgrade from a626b1c8d023 (#711).

Upgrade and downgrade invalidate all access/refresh credentials. Stop all old
application workers before upgrading; clients must sign in again.
"""

import sqlalchemy as sa
from alembic import op


def _clear_tokens() -> None:
    for table in ("users_refresh_token", "users_access_token"):
        op.execute(sa.table(table).delete())


def upgrade() -> None:
    _clear_tokens()
    with op.batch_alter_table("users_refresh_token") as batch:
        batch.alter_column(
            "token", existing_type=sa.Uuid(), type_=sa.String(64), postgresql_using="token::text"
        )
    with op.batch_alter_table("users_access_token") as batch:
        batch.alter_column("token", existing_type=sa.String(43), type_=sa.String(64))


def downgrade() -> None:
    # Digests cannot be restored to UUIDs or bearer secrets.
    _clear_tokens()
    with op.batch_alter_table("users_refresh_token") as batch:
        batch.alter_column(
            "token", existing_type=sa.String(64), type_=sa.Uuid(), postgresql_using="token::uuid"
        )
    with op.batch_alter_table("users_access_token") as batch:
        batch.alter_column("token", existing_type=sa.String(64), type_=sa.String(43))
