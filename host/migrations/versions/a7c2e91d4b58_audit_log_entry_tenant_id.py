"""audit_log_audit_entry: add nullable tenant_id

NULL means a platform action (no tenant bound when the row was written), which
is also what every pre-existing row is. The table is deliberately not
``MultiTenantMixin``: platform writes have no tenant and strict mode would
raise inside the flush. See GH #372.

Revision ID: a7c2e91d4b58
Revises: 70786227af4c
Create Date: 2026-10-01 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c2e91d4b58"
down_revision: str | None = "70786227af4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "audit_log_audit_entry"
_SINGLE = "ix_audit_log_audit_entry_tenant_id"
_COMPOSITE = "ix_audit_entry_tenant_created"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("tenant_id", sa.String(length=50), nullable=True))
        batch.create_index(_SINGLE, ["tenant_id"], unique=False)
        batch.create_index(_COMPOSITE, ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_index(_COMPOSITE)
        batch.drop_index(_SINGLE)
        batch.drop_column("tenant_id")
