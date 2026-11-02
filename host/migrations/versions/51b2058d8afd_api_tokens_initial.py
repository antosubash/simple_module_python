"""api_tokens: initial schema (personal access tokens and service keys)

One table for both credential kinds. Only the SHA-256 of a token is stored;
the unique key is ``(token_hash, tenant_id)`` — hash first, so a lookup by
hash alone is an index seek, and tenant in the key per SM024.

Revision ID: 51b2058d8afd
Revises: a659221c464b
Create Date: 2026-10-15 09:49:09.602365
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID

# revision identifiers, used by Alembic.
revision: str = "51b2058d8afd"
down_revision: str | None = "a659221c464b"
branch_labels: str | Sequence[str] | None = ("api_tokens",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens_token",
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", GUID(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens_token")),
    )
    op.create_index(
        "ix_api_tokens_token_hash_tenant",
        "api_tokens_token",
        ["token_hash", "tenant_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_api_tokens_token_owner_user_id"),
        "api_tokens_token",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_api_tokens_token_tenant_id"), "api_tokens_token", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_api_tokens_token_tenant_id"), table_name="api_tokens_token")
    op.drop_index(op.f("ix_api_tokens_token_owner_user_id"), table_name="api_tokens_token")
    op.drop_index("ix_api_tokens_token_hash_tenant", table_name="api_tokens_token")
    op.drop_table("api_tokens_token")
