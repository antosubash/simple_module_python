"""audit_log entity lookup index (#1166).

Revision ID: 819d8c5714a5
Revises: b8d4f2a6c901
Create Date: 2026-11-26 08:18:03.164696
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "819d8c5714a5"
down_revision: str | None = "b8d4f2a6c901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log_audit_entry") as batch:
        batch.create_index(
            "ix_audit_entry_entity_lookup", ["entity_type", "entity_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_log_audit_entry") as batch:
        batch.drop_index("ix_audit_entry_entity_lookup")
