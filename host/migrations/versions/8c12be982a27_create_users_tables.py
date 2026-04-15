"""create users tables

Revision ID: 8c12be982a27
Revises: 2fdcd367b517
Create Date: 2026-04-15 18:02:20.074558
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID, TIMESTAMPAware

# revision identifiers, used by Alembic.
revision: str = "8c12be982a27"
down_revision: str | None = "2fdcd367b517"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On PostgreSQL, create the `users` schema before creating tables.
    if op.get_context().dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS users")

    op.create_table(
        "users_role",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users_role")),
    )
    op.create_index(op.f("ix_users_role_name"), "users_role", ["name"], unique=True)

    op.create_table(
        "users_user",
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", GUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users_user")),
    )
    op.create_index(op.f("ix_users_user_email"), "users_user", ["email"], unique=True)
    op.create_index(op.f("ix_users_user_tenant_id"), "users_user", ["tenant_id"], unique=False)

    op.create_table(
        "users_access_token",
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("token", sa.String(length=43), nullable=False),
        sa.Column("created_at", TIMESTAMPAware(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users_user.id"],
            name=op.f("fk_users_access_token_user_id_users_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_users_access_token")),
    )
    op.create_index(
        op.f("ix_users_access_token_created_at"),
        "users_access_token",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "users_user_role",
        sa.Column("user_id", GUID(), nullable=False),
        sa.Column("role_id", GUID(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("assigned_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["users_role.id"],
            name=op.f("fk_users_user_role_role_id_users_role"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users_user.id"],
            name=op.f("fk_users_user_role_user_id_users_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_id", name=op.f("pk_users_user_role")),
    )


def downgrade() -> None:
    op.drop_table("users_user_role")
    op.drop_index(op.f("ix_users_access_token_created_at"), table_name="users_access_token")
    op.drop_table("users_access_token")
    op.drop_index(op.f("ix_users_user_tenant_id"), table_name="users_user")
    op.drop_index(op.f("ix_users_user_email"), table_name="users_user")
    op.drop_table("users_user")
    op.drop_index(op.f("ix_users_role_name"), table_name="users_role")
    op.drop_table("users_role")

    # On PostgreSQL, drop the `users` schema.
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP SCHEMA IF EXISTS users")
