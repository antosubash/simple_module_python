"""Read-side queries for stored files — listing, filtering, facets, totals.

Split out of ``service.py`` because they are a different job: nothing here
touches a storage backend or mutates a row, so the whole module is safe to call
from a view that only wants to render numbers. ``FileStorageService`` keeps
thin delegating methods so callers still go through one object.

Everything here is scoped by the caller's filters. The *unfiltered* bucket
totals — the byte usage and both facet lists, which describe the bucket rather
than the page — live in :mod:`file_storage.aggregates`, where one grouped scan
answers all three and the result can be cached.
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


async def count_files(
    db: AsyncSession,
    *,
    created_by: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
) -> int:
    """How many rows the filters match.

    Split from :func:`page_of_files` so a caller that has to clamp ``?page=``
    can learn the total *before* choosing an offset. Asking for the page first
    and re-asking after the clamp — which is what the browse view used to do —
    paid for a page of rows nobody would ever see.
    """
    # ``func.count(StoredFile.id)``, not a bare ``func.count()``: the
    # soft-delete loader criteria are attached per *mapper found in the
    # statement*, and a bare count with only ``select_from`` names no mapped
    # column, so the filter never applied and the total went on counting
    # deleted rows. That is the pager offering pages that render empty — the
    # exact failure ``filter_clauses`` exists to prevent.
    query = select(func.count(StoredFile.id)).select_from(StoredFile)
    for clause in filter_clauses(created_by=created_by, search=search, content_type=content_type):
        query = query.where(clause)
    return int((await db.execute(query)).scalar() or 0)


async def page_of_files(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    created_by: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
) -> list[StoredFileOut]:
    """One page of rows, newest first, narrowed by the same filters as the count."""
    query = select(StoredFile)
    for clause in filter_clauses(created_by=created_by, search=search, content_type=content_type):
        query = query.where(clause)
    result = await db.execute(
        query.order_by(StoredFile.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return [StoredFileOut.model_validate(to_out_dict(r)) for r in result.scalars().all()]


async def list_files(
    db: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    created_by: str | None = None,
    search: str | None = None,
    content_type: str | None = None,
) -> tuple[list[StoredFileOut], int]:
    """Page plus total, for callers whose page number is already known good.

    The JSON API is one: it bounds ``page`` with ``Query(ge=1)`` and returns a
    422 rather than clamping, so it never needs the count before the rows.
    """
    filters = {"created_by": created_by, "search": search, "content_type": content_type}
    total = await count_files(db, **filters)
    items = await page_of_files(db, page=page, per_page=per_page, **filters)
    return items, total


async def content_type_facets(db: AsyncSession, *, created_by: str | None = None) -> list[dict]:
    """Distinct content types present for one uploader, with counts.

    Offering the full IANA list would be noise; the only types worth showing
    are the ones actually in the bucket. The unfiltered case — what the browse
    dropdown actually renders — is answered from
    :func:`file_storage.aggregates.compute` instead, which gets it out of the
    same scan as the uploader facets and the byte total.
    """
    query = select(StoredFile.content_type, func.count().label("n"))
    for clause in filter_clauses(created_by=created_by, search=None, content_type=None):
        query = query.where(clause)
    query = query.group_by(StoredFile.content_type).order_by(StoredFile.content_type)

    rows = (await db.execute(query)).all()
    return [{"value": str(row[0]), "count": int(row[1])} for row in rows]


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
