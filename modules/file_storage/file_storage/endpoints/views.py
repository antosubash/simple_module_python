"""Inertia view endpoints for the file_storage module."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from simple_module_db.deps import get_db
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants
from file_storage.aggregates import StorageAggregates
from file_storage.contracts.schemas import StoredFileOut
from file_storage.deps import OwnerScope, get_file_storage_service
from file_storage.resolve import label_for, resolve_uploader_labels
from file_storage.service import FileStorageService

router = APIRouter()

_PER_PAGE = 20


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def browse(
    inertia: InertiaDep,
    page: int = Query(default=1),
    q: str = "",
    content_type: str = "",
    uploaded_by: str = "",
    db: AsyncSession = Depends(get_db),
    service: FileStorageService = Depends(get_file_storage_service),
    owner: str | None = OwnerScope,
) -> InertiaResponse:
    # A user-supplied page below 1 (0, negative, a hand-edited ?page=) must
    # clamp to the first page rather than reject — mirrors the past-the-end
    # clamp below so no value of ?page= can produce a raw validation-error
    # page for a browser-facing route.
    page = max(page, 1)
    filters = {
        "search": q or None,
        "content_type": content_type or None,
        # Without file_storage.manage the screen is the caller's own uploads
        # (#544); the uploader filter cannot widen it.
        "created_by": owner if owner is not None else (uploaded_by or None),
    }
    # Count before paging, not after. A page requested past the end (reloading
    # after deleting the last row on that page, or a stale ?page= link) must be
    # clamped — otherwise the client gets an empty `files` list with a nonzero
    # `total`, which satisfies neither the "no results" empty state nor the
    # "more than one page" pager condition and renders a blank table. Asking
    # for the rows first meant fetching, and throwing away, a page nobody would
    # ever see; the total is what decides which page to fetch, so it goes first.
    total = await service.count_files(**filters)
    total_pages = max(1, math.ceil(total / _PER_PAGE))
    page = min(page, total_pages)
    items = await service.page_of_files(page=page, per_page=_PER_PAGE, **filters)
    # The bucket-wide numbers — usage and both facet lists — come from one
    # scan, cached with a short TTL. They ignore the active filters so the
    # dropdowns keep offering the other types and people (a filter that hides
    # its own alternatives is a dead end) and so the usage figure keeps
    # describing the bucket rather than the search box.
    aggregates = await service.storage_aggregates()
    content_types, uploaders = await _facets(service, aggregates, owner)
    # One lookup covers the rows on screen and the filter's options, so
    # picking someone from the dropdown never renames them.
    labels = await resolve_uploader_labels(
        db, [item.uploaded_by for item in items] + [u["id"] for u in uploaders]
    )
    settings = service.settings
    # The page name is hard-coded as a literal here (rather than via
    # ``constants.PAGE_BROWSE``) so the SM003/SM004 diagnostics — which do
    # static AST analysis and cannot resolve attribute access — pair this
    # call with ``pages/Browse.tsx``. A unit test asserts the literal
    # matches ``constants.PAGE_BROWSE``.
    return await inertia.render(
        "FileStorage/Browse",
        {
            "files": [_file_payload(item, labels) for item in items],
            "pagination": {"page": page, "perPage": _PER_PAGE, "total": total},
            "filters": {"q": q, "content_type": content_type, "uploaded_by": uploaded_by},
            "content_types": content_types,
            "uploaders": [{**u, "label": label_for(u["id"], labels)} for u in uploaders],
            # What the header subtitle states about the bucket. ``quota_bytes``
            # stays None until an operator says what the ceiling is — the
            # screen reports usage rather than inventing a total.
            "backend": settings.backend,
            # The quota measures the tenant, so only callers who see the whole
            # tenant get it; everyone else sees their own usage, no ceiling.
            "used_bytes": (
                aggregates.used_bytes if owner is None else await service.used_bytes_by(owner)
            ),
            "quota_bytes": settings.quota_bytes if owner is None else None,
            "max_file_size_bytes": settings.max_file_size_bytes,
            # Above this the page uploads in resumable parts; null when the
            # backend cannot (a third-party one without multipart support).
            "direct_upload_threshold_bytes": (
                settings.direct_upload_threshold_bytes
                if getattr(service.backend, "supports_direct_upload", False)
                else None
            ),
            "max_direct_upload_bytes": settings.max_direct_upload_bytes,
            "allowed_content_types": settings.allowed_content_types,
        },
    )


async def _facets(
    service: FileStorageService, aggregates: StorageAggregates, owner: str | None
) -> tuple[list[dict], list[dict]]:
    """The type and uploader dropdowns: bucket-wide, or the caller's own slice.

    A caller confined to their own files must not learn who else uploaded what
    from the facet lists either, so theirs come from their rows alone. The
    usage figure stays bucket-wide: the quota it is measured against is.
    """
    if owner is None:
        return (
            [facet.as_dict() for facet in aggregates.content_types],
            [{"id": f.value, "count": f.count} for f in aggregates.uploaders],
        )
    content_types = await service.content_type_facets(created_by=owner)
    total = sum(facet["count"] for facet in content_types)
    return content_types, ([{"id": owner, "count": total}] if total else [])


def _file_payload(item: StoredFileOut, labels: dict[str, str]) -> dict:
    """One row, with its uploader resolved to something readable."""
    payload = item.model_dump(mode="json")
    payload["uploaded_by_label"] = label_for(item.uploaded_by, labels)
    return payload
