"""users: one local link per OAuth identity (#1153).

Revision ID: b1153e9c7b62
Revises: a1054e9c7b62
Create Date: 2026-11-26 07:08:21.880485
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1153e9c7b62"
down_revision: str | None = "a1054e9c7b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    links = sa.table(
        "users_oauth_account",
        *(sa.column(c) for c in ("id", "user_id", "oauth_name", "account_id")),
    )
    users = sa.table("users_user", sa.column("id"), sa.column("email"))
    identity = (links.c.oauth_name, links.c.account_id)
    duplicates = sa.select(*identity).group_by(*identity).having(sa.func.count() > 1)
    conflicts = op.get_bind().execute(
        sa.select(*identity, links.c.user_id, users.c.email, links.c.id)
        .select_from(links.outerjoin(users, users.c.id == links.c.user_id))
        .where(sa.tuple_(*identity).in_(duplicates))
        .order_by(*identity, links.c.user_id, links.c.id)
    )
    listed = [
        f"({provider!r}, {account_id!r}): {email!r} (user {user_id}, link {link_id})"
        for provider, account_id, user_id, email, link_id in conflicts
    ]
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
