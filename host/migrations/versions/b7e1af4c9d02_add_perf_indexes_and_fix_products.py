"""Add perf indexes and drop low-cardinality boolean index.

Creates:
  * ``ix_users_user_email_lower`` — functional index on ``lower(email)`` so the
    fastapi-users ``get_by_email`` query (which wraps email in ``lower()``)
    can use an index instead of a seq-scan.
  * ``ix_users_access_token_user_id`` — Postgres does not auto-index foreign
    keys; this covers reverse lookups (e.g. revoking a user's sessions).
  * ``ix_users_user_role_role_id`` — same reasoning for "who has role X?"
    queries. The composite PK already covers ``user_id``-first lookups.
  * ``ix_products_product_deleted`` — supports soft-delete filtering in the
    product listing query.

Drops:
  * ``ix_products_product_is_active`` — a plain B-tree over a 2-value boolean
    is almost never preferred by the planner over a seq-scan, yet it costs
    writes on every insert/update. Replaced implicitly by the combined
    filtering the ``products_product_deleted`` index covers.

PostgreSQL path uses ``CREATE INDEX CONCURRENTLY`` via ``postgresql_concurrently``
+ ``autocommit_block`` so index builds on large tables do not block writes.
SQLite ignores the flag (its ``CREATE INDEX`` is already fast and non-locking
for this workload).

Revision ID: b7e1af4c9d02
Revises: a01185374312
Create Date: 2026-04-16 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e1af4c9d02"
down_revision: str | None = "a01185374312"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Functional index: ``lower(email)``. Using a literal SQL expression keeps
# the syntax identical on Postgres and SQLite; SQLAlchemy's ``text()`` is
# escaped appropriately by the dialect in both cases.
_EMAIL_LOWER_EXPR = sa.text("lower(email)")


def upgrade() -> None:
    is_postgres = op.get_context().dialect.name == "postgresql"

    # Each ``CREATE/DROP INDEX CONCURRENTLY`` auto-commits as soon as it finishes.
    # ``if_exists`` / ``if_not_exists`` make the migration re-runnable after a
    # partial failure mid-block: otherwise we'd have to manually clean up the
    # already-committed indexes before retrying.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_users_user_email_lower",
            "users_user",
            [_EMAIL_LOWER_EXPR],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.create_index(
            "ix_users_access_token_user_id",
            "users_access_token",
            ["user_id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.create_index(
            "ix_users_user_role_role_id",
            "users_user_role",
            ["role_id"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.create_index(
            "ix_products_product_is_deleted",
            "products_product",
            ["is_deleted"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.drop_index(
            "ix_products_product_is_active",
            table_name="products_product",
            if_exists=True,
            postgresql_concurrently=is_postgres,
        )


def downgrade() -> None:
    is_postgres = op.get_context().dialect.name == "postgresql"

    with op.get_context().autocommit_block():
        op.create_index(
            "ix_products_product_is_active",
            "products_product",
            ["is_active"],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.drop_index(
            "ix_products_product_is_deleted",
            table_name="products_product",
            if_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.drop_index(
            "ix_users_user_role_role_id",
            table_name="users_user_role",
            if_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.drop_index(
            "ix_users_access_token_user_id",
            table_name="users_access_token",
            if_exists=True,
            postgresql_concurrently=is_postgres,
        )
        op.drop_index(
            "ix_users_user_email_lower",
            table_name="users_user",
            if_exists=True,
            postgresql_concurrently=is_postgres,
        )
