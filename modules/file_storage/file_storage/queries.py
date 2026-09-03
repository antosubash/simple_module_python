"""Read-side queries for stored files — listing, filtering, facets, totals.

Split out of ``service.py`` because they are a different job: nothing here
touches a storage backend or mutates a row, so the whole module is safe to call
from a view that only wants to render numbers. ``FileStorageService`` keeps
thin delegating methods so callers still go through one object.
"""

from __future__ import annotations

from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern, like_prefix_pattern
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage.contracts.schemas import StoredFileOut
from file_storage.models import StoredFile


def filter_clauses(
    *,
    created_by: str | None,
    search: str | None,
    content_type: str | None,
) -> list:
    """Build the WHERE clauses shared by the page query and its count.

    Kept in one place so a filter can never narrow the rows without also
    narrowing the total — the bug that shows up as a pager offering page 3
    of an empty search.
    """
    clauses = []
    if created_by is not None:
        clauses.append(StoredFile.created_by == created_by)
    if search:
        # Escape LIKE metacharacters so a literal "%" or "_" in a
        # filename search is matched as text, not treated as a wildcard.
        clauses.append(
            StoredFile.filename.ilike(like_contains_pattern(search), escape=LIKE_ESCAPE_CHAR)
        )
    if content_type:
        # A trailing "/" means a whole family ("image/"), anything else is
        # an exact type ("application/pdf"). Families are what make the
        # filter usable when a bucket holds nine kinds of image.
        if content_type.endswith("/"):
            clauses.append(
                StoredFile.content_type.ilike(
                    like_prefix_pattern(content_type), escape=LIKE_ESCAPE_CHAR
                )
            )
        else:
            clauses.append(StoredFile.content_type == content_type)
    return clauses


async def list_files(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    created_by: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
) -> tuple[list[StoredFileOut], int]:
    base = select(StoredFile)
    # ``func.count(StoredFile.id)``, not a bare ``func.count()``: the
    # soft-delete loader criteria are attached per *mapper found in the
    # statement*, and a bare count with only ``select_from`` names no mapped
    # column, so the filter never applied and the total went on counting
    # deleted rows. That is the pager offering pages that render empty — the
    # exact failure ``filter_clauses`` exists to prevent.
    count_q = select(func.count(StoredFile.id)).select_from(StoredFile)
    for clause in filter_clauses(created_by=created_by, search=search, content_type=content_type):
        base = base.where(clause)
        count_q = count_q.where(clause)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        base.order_by(StoredFile.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    rows = result.scalars().all()
    return [StoredFileOut.model_validate(to_out_dict(r)) for r in rows], total


async def content_type_facets(db: AsyncSession, *, created_by: str | None = None) -> list[dict]:
    """Distinct content types present, with counts, for the filter dropdown.

    Offering the full IANA list would be noise; the only types worth
    showing are the ones actually in the bucket.
    """
    query = select(StoredFile.content_type, func.count().label("n"))
    for clause in filter_clauses(created_by=created_by, search=None, content_type=None):
        query = query.where(clause)
    query = query.group_by(StoredFile.content_type).order_by(StoredFile.content_type)

    rows = (await db.execute(query)).all()
    return [{"value": str(row[0]), "count": int(row[1])} for row in rows]


async def uploader_facets(db: AsyncSession) -> list[dict]:
    """Distinct uploaders present, with counts, for the "Uploaded by" filter.

    Rows with no ``created_by`` — anything uploaded before the audit listener
    had a user to record — are skipped rather than offered under a sentinel:
    ``created_by=None`` already means "every uploader" to the listing query, so
    a "no uploader" option could not be honestly round-tripped through the
    query string.
    """
    query = (
        select(StoredFile.created_by, func.count().label("n"))
        .where(StoredFile.created_by.is_not(None))
        .group_by(StoredFile.created_by)
        .order_by(StoredFile.created_by)
    )
    rows = (await db.execute(query)).all()
    return [{"value": str(row[0]), "count": int(row[1])} for row in rows]


async def used_bytes(db: AsyncSession) -> int:
    """Total bytes held by files that still exist.

    Deliberately ignores the active filters: this describes the bucket, not the
    page being looked at, and a number that shrank when someone typed in the
    search box would be describing nothing at all. Deleted rows are excluded by
    the soft-delete loader criteria, so a deleted file stops counting against
    the quota the moment it goes.
    """
    total = (await db.execute(select(func.coalesce(func.sum(StoredFile.size_bytes), 0)))).scalar()
    return int(total or 0)


def to_out_dict(row: StoredFile) -> dict:
    """Project ORM row → DTO dict, mapping ``created_by`` to ``uploaded_by``."""
    return {
        "id": row.id,
        "key": row.key,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "backend": row.backend,
        "checksum_sha256": row.checksum_sha256,
        "uploaded_by": row.created_by,
        "created_at": row.created_at,
    }
