"""Turn share rows into ``ShareOut`` with user labels from the directory."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from simple_module_core.resources import ResourcePrincipal
from simple_module_core.user_directory import UserDirectory, resolve_user_labels

from sharing.contracts.schemas import ShareOut
from sharing.contracts.subjects import SubjectContext, SubjectRegistry
from sharing.core.audience import Audience, OpenAudience
from sharing.core.constants import SUBJECT_USER
from sharing.core.subjects import subjects_for
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
    principal: ResourcePrincipal | None = None,
    subjects: SubjectRegistry | None = None,
) -> list[ShareOut]:
    """One batched directory lookup for every subject and granter on the page.

    Only users in the request's *audience* (the active tenant's members) are
    named; anyone else shows as their raw id, so no label crosses tenants.
    """
    principal = principal or ResourcePrincipal(None)
    subjects = subjects if subjects is not None else subjects_for(principal)
    ctx = SubjectContext(db, directory, audience, principal)
    ids = [s.subject_id for s in shares if s.subject_type == SUBJECT_USER] + [
        s.granted_by for s in shares
    ]
    labels = await resolve_user_labels(directory, db, await audience.visible(ids))
    subject_labels = {SUBJECT_USER: labels}
    for provider in subjects.all():
        if provider.name == SUBJECT_USER:
            continue
        wanted = {s.subject_id for s in shares if s.subject_type == provider.name}
        if wanted:
            subject_labels[provider.name] = await provider.labels(ctx, wanted)
    now = datetime.now(UTC)
    return [
        ShareOut.model_validate(
            share,
            update={
                "subject_label": subject_labels.get(share.subject_type, {}).get(share.subject_id),
                "granted_by_label": labels.get(share.granted_by),
                "expired": _expired(share, now),
            },
        )
        for share in shares
    ]
