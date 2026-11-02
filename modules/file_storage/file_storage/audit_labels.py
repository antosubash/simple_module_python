"""Audit-log label resolver for stored files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _resolve_file_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Name a stored file by its filename — "q3-report.pdf", not a uuid.

    Ids that are not uuids belong to some other id space and are left unnamed,
    which falls back to showing the id as stored.
    """
    import uuid as _uuid

    from sqlalchemy import select

    from file_storage.models import StoredFile

    wanted: dict[_uuid.UUID, str] = {}
    for raw in ids:
        try:
            wanted[_uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not wanted:
        return {}
    # Deliberately cross-tenant: the audit log is a platform screen listing
    # every tenant's entries, and the entry it labels already records the
    # filename among its captured fields, so naming it discloses nothing new.
    # Scoped to the bound tenant instead, it would fail closed for a platform
    # admin with no organisation and leave every other tenant's file a uuid.
    stmt = select(StoredFile.id, StoredFile.filename).where(StoredFile.id.in_(list(wanted)))
    rows = (await db.execute(stmt.execution_options(all_tenants=True))).all()
    return {wanted.get(file_id, str(file_id)): filename for file_id, filename in rows}
