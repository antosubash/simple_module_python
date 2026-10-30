"""Task resource references (#709).

Revision ID: b31a70971001
Revises: a626b1c8d023 (background_tasks@head)
"""

import sqlalchemy as sa
from alembic import op

revision = "b31a70971001"
down_revision = "a626b1c8d023"
branch_labels = None
depends_on = None

_TABLE = "background_tasks_task_execution"
_CONSTRAINT = "ck_background_tasks_task_execution_task_resource_pair"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("resource_type", sa.String(255), nullable=True))
        batch.add_column(sa.Column("resource_id", sa.String(255), nullable=True))
        batch.create_check_constraint(
            op.f(_CONSTRAINT), "(resource_type IS NULL) = (resource_id IS NULL)"
        )


def downgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(op.f(_CONSTRAINT), type_="check")
        batch.drop_column("resource_id")
        batch.drop_column("resource_type")
