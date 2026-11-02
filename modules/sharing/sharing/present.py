"""Turn share rows into ``ShareOut`` with user labels from the directory."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from simple_module_core.user_directory import UserDirectory, resolve_user_labels

from sharing.audience import Audience, OpenAudience
from sharing.contracts.schemas import ShareOut
from sharing.models import ResourceShare


def _expired(share: ResourceShare, now: datetime) -> bool:
    if share.expires_at is None:
        return False
    expires = share.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= now


async def present_shares(
    directory: UserDirectory,
    db: Any,
    shares: Sequence[ResourceShare],
    audience: Audience | OpenAudience,
) -> list[ShareOut]:
    """One batched directory lookup for every subject and granter on the page.

    Only users in the request's *audience* (the active tenant's members) are
    named; anyone else shows as their raw id, so no label crosses tenants.
    """
    ids = [s.subject_id for s in shares] + [s.granted_by for s in shares]
    labels = await resolve_user_labels(directory, db, await audience.visible(ids))
    now = datetime.now(UTC)
    return [
        ShareOut.model_validate(
            share,
            update={
                "subject_label": labels.get(share.subject_id),
                "granted_by_label": labels.get(share.granted_by),
                "expired": _expired(share, now),
            },
        )
        for share in shares
    ]
