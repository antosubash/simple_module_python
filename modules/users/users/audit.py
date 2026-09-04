"""How a user row is named, and reached, from the audit log.

An audit entry stores ``User`` and a uuid. Turning that back into something a
reader can act on has two halves and both belong here: *where* the record
lives (the admin route) and *what it is called*. Only this module knows the
second — a user is named by ``full_name``, or by the email while an invite is
still outstanding and no name exists yet.

The resolver is deliberately batched: an audit page is 50 rows and a busy
afternoon is 50 edits to the same handful of accounts, so it takes every id on
the page and answers in one query.
"""

from __future__ import annotations

import uuid

from simple_module_core.audit_links import AuditLink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from users.models import User

_LABEL = "User"
_LABEL_KEY = "users.audit.user"


async def resolve_user_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Map user id -> display name for every id given.

    Ids that do not parse as uuids belong to some other id space (a worker
    name, say) and ids that no longer resolve belong to deleted accounts.
    Both are simply absent from the result rather than an error: the caller
    falls back to the raw id, which is still the truthful record.
    """
    parsed: dict[uuid.UUID, str] = {}
    for raw in ids:
        try:
            parsed[uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not parsed:
        return {}

    rows = (
        await db.execute(
            select(User.id, User.email, User.full_name).where(User.id.in_(list(parsed)))
        )
    ).all()
    return {
        parsed.get(user_id, str(user_id)): (full_name or email)
        for user_id, email, full_name in rows
    }


def build_user_audit_link(admin_url_prefix: str) -> AuditLink:
    """The registry entry for user rows, rooted at the module's admin route."""
    return AuditLink(
        # The model class name — what snapshot_changes records. Keying this
        # off __tablename__ ("users_user") silently never matches; the table
        # name travels alongside, as the tag shown beside the row's name.
        entity_type=User.__name__,
        url_template=f"{admin_url_prefix}{{id}}",
        label=_LABEL,
        label_key=_LABEL_KEY,
        table_name=User.__tablename__,
        label_resolver=resolve_user_labels,
    )
