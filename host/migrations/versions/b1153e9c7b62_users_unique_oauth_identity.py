"""users: one local link per OAuth identity (#1153).

Revision ID: b1153e9c7b62
Revises: a1054e9c7b62
Create Date: 2026-11-26 07:08:21.880485
"""

from collections.abc import Sequence

from alembic import op
from users.core.data_compatibility import oauth_identity_conflicts_query

# revision identifiers, used by Alembic.
revision: str = "b1153e9c7b62"
down_revision: str | None = "a1054e9c7b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SHOWN_CONFLICTS = 20


def upgrade() -> None:
    conflicts = (
        op.get_bind().execute(oauth_identity_conflicts_query().limit(_SHOWN_CONFLICTS + 1)).all()
    )
    listed = [
        f"({provider!r}, {account_id!r}): {email!r} (user {user_id}, link {link_id})"
        for provider, account_id, user_id, email, link_id in conflicts[:_SHOWN_CONFLICTS]
    ]
    if len(conflicts) > _SHOWN_CONFLICTS:
        listed.append(
            f"More conflicting links exist; showing the first {_SHOWN_CONFLICTS}. "
            "Resolve them and rerun to list more."
        )
    if listed:
        # SM010 runs before SM033 on an upgrade: refuse with remediation before DDL.
        raise RuntimeError(
            "Cannot enforce unique OAuth identities (oauth_name, account_id):\n"
            + "\n".join(listed)
            + "\nBefore upgrading, open each affected user's admin Edit page in the previous "
            "app version (Users → user → Linked sign-ins → Remove) and remove the extra "
            "links, keeping one link per identity. Stop old workers and retry migrations. "
            "No links or users are removed automatically."
        )
    with op.batch_alter_table("users_oauth_account") as batch:
        batch.create_unique_constraint(
            "uq_users_oauth_account_identity", ["oauth_name", "account_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("users_oauth_account") as batch:
        batch.drop_constraint("uq_users_oauth_account_identity", type_="unique")
