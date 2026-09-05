"""Inertia view endpoints for the file_storage module."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from inertia import InertiaResponse
from simple_module_db.deps import get_db
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage import constants
from file_storage.contracts.schemas import StoredFileOut
from file_storage.deps import get_file_storage_service
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
) -> InertiaResponse:
    # A user-supplied page below 1 (0, negative, a hand-edited ?page=) must
    # clamp to the first page rather than reject — mirrors the past-the-end
    # clamp below so no value of ?page= can produce a raw validation-error
    # page for a browser-facing route.
    page = max(page, 1)
    filters = {
        "search": q or None,
        "content_type": content_type or None,
        "created_by": uploaded_by or None,
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
    # One lookup covers the rows on screen and the filter's options, so
    # picking someone from the dropdown never renames them.
    labels = await resolve_uploader_labels(
        db,
        [item.uploaded_by for item in items] + [f.value for f in aggregates.uploaders],
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
            "content_types": [facet.as_dict() for facet in aggregates.content_types],
            "uploaders": [
                {"id": f.value, "label": label_for(f.value, labels), "count": f.count}
                for f in aggregates.uploaders
            ],
            # What the header subtitle states about the bucket. ``quota_bytes``
            # stays None until an operator says what the ceiling is — the
            # screen reports usage rather than inventing a total.
            "backend": settings.backend,
            "used_bytes": aggregates.used_bytes,
            "quota_bytes": settings.quota_bytes,
            "max_file_size_bytes": settings.max_file_size_bytes,
            "allowed_content_types": settings.allowed_content_types,
        },
    )


def _file_payload(item: StoredFileOut, labels: dict[str, str]) -> dict:
    """One row, with its uploader resolved to something readable."""
    payload = item.model_dump(mode="json")
    payload["uploaded_by_label"] = label_for(item.uploaded_by, labels)
    return payload
