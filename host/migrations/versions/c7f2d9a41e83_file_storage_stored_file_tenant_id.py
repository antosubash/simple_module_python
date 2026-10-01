"""file_storage_stored_file: adopt MultiTenantMixin

Adds ``tenant_id`` (nullable → back-filled with ``DEFAULT_TENANT_ID`` → NOT
NULL), indexes it, and widens the unique ``key`` index to ``(tenant_id, key)``
so two tenants can hold the same key (SM024). Existing rows keep their key:
the column stores the full object path, so their bytes are still found where
they were written; only new uploads get the ``{tenant_id}/`` prefix. See
GH #383.

Back-filled rows land in the default tenant, which is also what
``file_storage`` treats as the *platform* owner — so branding images uploaded
before this migration stay readable from the anonymous asset routes.

file_storage has no migration chain of its own (its table came in with the
host's initial schema), so this extends the mainline head.

Revision ID: c7f2d9a41e83
Revises: b5d3f08a6e17
Create Date: 2026-10-01 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from simple_module_db import DEFAULT_TENANT_ID

# revision identifiers, used by Alembic.
revision: str = "c7f2d9a41e83"
down_revision: str | None = "b5d3f08a6e17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "file_storage_stored_file"
_OLD_KEY = "ix_file_storage_stored_file_key"
_TENANT_KEY = "ix_file_storage_stored_file_tenant_key"
_TENANT = "ix_file_storage_stored_file_tenant_id"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("tenant_id", sa.String(length=50), nullable=True))
    op.execute(
        sa.text(f"UPDATE {_TABLE} SET tenant_id = :t WHERE tenant_id IS NULL").bindparams(
            t=DEFAULT_TENANT_ID
        )
    )
    with op.batch_alter_table(_TABLE) as batch:
        batch.alter_column("tenant_id", existing_type=sa.String(length=50), nullable=False)
        batch.drop_index(_OLD_KEY)
        batch.create_index(_TENANT_KEY, ["tenant_id", "key"], unique=True)
        batch.create_index(_TENANT, ["tenant_id"], unique=False)


def downgrade() -> None:
    # Fails if two tenants hold the same key — only possible for keys written
    # by hand, since generated keys carry a uuid. Resolve those rows first.
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_index(_TENANT)
        batch.drop_index(_TENANT_KEY)
        batch.create_index(_OLD_KEY, ["key"], unique=True)
        batch.drop_column("tenant_id")
