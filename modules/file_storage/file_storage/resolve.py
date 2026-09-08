"""Turn the user id stored on a file row into a name a reader recognises.

``StoredFile.created_by`` holds an opaque user id. That is right for a
permanent record — display names change, ids do not — and useless in a table:
a column of uuids names nobody.

The users module is imported lazily and optionally. ``file_storage`` does not
depend on it: an install can run an external identity provider instead, in
which case the ids belong to another id space and the screen falls back to
showing what it stored rather than failing the page. Precedent:
``modules/audit_log/audit_log/resolve.py``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants


async def resolve_uploader_labels(
    db: AsyncSession, user_ids: Iterable[str | None]
) -> dict[str, str]:
    """Map user id -> display label for every id on the page.

    One query for the whole page rather than one per row: a file listing is 20
    rows and the same handful of people tend to have uploaded all of them.

    Ids that no longer resolve — deleted accounts, or another provider's id
    space — are simply absent from the result; the caller falls back to the raw
    id, which is still the truthful record of who uploaded the file.
    """
    wanted = {uid for uid in user_ids if uid}
    if not wanted:
        return {}

    try:
        from users.models import User
    except ImportError:
        return {}

    # File rows store the id as text; the users table keys on UUID. Ids that
    # aren't parseable belong to some other id space, so skip rather than fail.
    parsed: dict[uuid.UUID, str] = {}
    for raw in wanted:
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
        (parsed.get(user_id) or str(user_id)): (full_name or email)
        for user_id, email, full_name in rows
    }


def label_for(user_id: str | None, labels: dict[str, str]) -> str:
    """Display label for one row's uploader.

    ``None`` is a different thing from "unresolved": no uploader was ever
    recorded, so there is no id to fall back to and the cell reads as unknown.
    """
    if not user_id:
        return constants.UNKNOWN_UPLOADER
    return labels.get(user_id, user_id)
