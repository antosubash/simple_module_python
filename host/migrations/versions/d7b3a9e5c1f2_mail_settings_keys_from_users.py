"""move the users mailer settings to the mail module

Revision ID: d7b3a9e5c1f2
Revises: c8e4f1a2b6d9
Create Date: 2026-10-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7b3a9e5c1f2"
down_revision: str | None = "c8e4f1a2b6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SMTP transport and its settings moved from ``users`` to the ``mail`` module
# (GH #496). Data only: rewrites the key of system-scope rows in the settings
# table. An existing target row wins, so a re-run (or an admin who already set
# the new keys) is safe and the stale row is simply dropped.

_TABLE = "settings_setting"
_SCOPE_SYSTEM = "system"
_SYSTEM_SCOPE_ID = ""

_KEY_PAIRS = (
    ("users.mailer", "mail.backend"),
    *((f"users.smtp_{f}", f"mail.smtp_{f}") for f in ("host", "port", "username", "password")),
    ("users.smtp_from", "mail.smtp_from"),
    ("users.smtp_tls", "mail.smtp_tls"),
)


def _rename(old: str, new: str) -> None:
    scope = {"scope": _SCOPE_SYSTEM, "scope_id": _SYSTEM_SCOPE_ID, "old": old, "new": new}
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"DELETE FROM {_TABLE} WHERE scope = :scope AND scope_id = :scope_id AND key = :old"
            f" AND EXISTS (SELECT 1 FROM {_TABLE} AS t WHERE t.scope = :scope"
            " AND t.scope_id = :scope_id AND t.key = :new)"
        ),
        scope,
    )
    bind.execute(
        sa.text(
            f"UPDATE {_TABLE} SET key = :new"
            " WHERE scope = :scope AND scope_id = :scope_id AND key = :old"
        ),
        scope,
    )


def upgrade() -> None:
    for old, new in _KEY_PAIRS:
        _rename(old, new)


def downgrade() -> None:
    for old, new in _KEY_PAIRS:
        _rename(new, old)
