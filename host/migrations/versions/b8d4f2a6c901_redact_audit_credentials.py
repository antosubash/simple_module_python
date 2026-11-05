"""Harden historical audit credential values.

Revision ID: b8d4f2a6c901
Revises: a7c2e91d4b58
"""

import sqlalchemy as sa
from alembic import op

revision = "b8d4f2a6c901"
down_revision = "a7c2e91d4b58"
branch_labels = None
depends_on = None

# Frozen policy: historical settings entries may lack their key or declared
# type, so all historical setting values are redacted conservatively.
_REDACTED = "[redacted]"
_FIELDS = {
    "Setting": {"value"},
    "LeaseRow": {"holder"},
    "User": {"hashed_password"},
    "OAuthAccount": {"access_token", "refresh_token"},
    "Invitation": {"token_hash"},
    "ApiToken": {"token_hash"},
    "UserAccessToken": {"token"},
    "RefreshToken": {"token"},
    "RefreshOutcome": {"session", "outcome_key", "lock_key"},
}
_REDACT_IDS = {"UserAccessToken", "RefreshToken", "RefreshOutcome"}


def upgrade() -> None:
    conn = op.get_bind()
    audit = sa.Table("audit_log_audit_entry", sa.MetaData(), autoload_with=conn)
    # Keyset batches bound memory and close each cursor before updating rows.
    last_id = None
    while True:
        query = (
            sa.select(audit).where(audit.c.entity_type.in_(_FIELDS)).order_by(audit.c.id).limit(500)
        )
        if last_id is not None:
            query = query.where(audit.c.id > last_id)
        rows = conn.execute(query).mappings().all()
        if not rows:
            break
        for row in rows:
            changes = row["changes"]
            fields = _FIELDS[row["entity_type"]]
            if isinstance(changes, list):
                changes = [
                    {
                        k: _REDACTED if c.get("field") in fields and k in {"old", "new"} else v
                        for k, v in c.items()
                    }
                    if isinstance(c, dict)
                    else c
                    for c in changes
                ]
            elif isinstance(changes, dict):
                changes = {k: _REDACTED if k in fields else v for k, v in changes.items()}
            identity = _REDACTED if row["entity_type"] in _REDACT_IDS else row["entity_id"]
            if changes != row["changes"] or identity != row["entity_id"]:
                conn.execute(
                    audit.update()
                    .where(audit.c.id == row["id"])
                    .values(changes=changes, entity_id=identity)
                )
        last_id = rows[-1]["id"]


def downgrade() -> None:
    # Credential values are intentionally unrecoverable; retain the hardened trail.
    pass
