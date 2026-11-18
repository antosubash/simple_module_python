"""Inertia view endpoints for the file_storage module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from simple_module_core.user_directory import get_user_directory
from simple_module_db.deps import get_db
from simple_module_db.pagination import PageParams, clamp_page
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.pagination import lenient_page_params
from simple_module_hosting.permissions import RequiresPermission
from simple_module_inertia import InertiaResponse
from sqlalchemy.ext.asyncio import AsyncSession

from file_storage.contracts.schemas import StoredFileOut
from file_storage.core import constants
from file_storage.files.resolve import label_for, resolve_uploader_labels
from file_storage.files.service import FileStorageService
from file_storage.web.deps import OwnerScope, get_authorized_file_storage_service

router = APIRouter()

_PER_PAGE = 20


@router.get(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.Permission.DOWNLOAD))],
)
async def browse(
    request: Request,
    inertia: InertiaDep,
    params: PageParams = Depends(lenient_page_params(_PER_PAGE)),
    q: str = "",
    content_type: str = "",
    uploaded_by: str = "",
    db: AsyncSession = Depends(get_db),
    service: FileStorageService = Depends(get_authorized_file_storage_service),
    owner: str | None = OwnerScope,
) -> InertiaResponse:
    # ``lenient_page_params`` clamps a page below 1 (0, negative, a hand-edited
    # ?page=) to the first page, so no ?page= value can produce a raw
    # validation-error page for a browser-facing route.
    filters = {
        "search": q or None,
        "content_type": content_type or None,
        # The service policy supplies row visibility; this only narrows the search.
        # Retain the legacy rule that members cannot override the uploader filter.
        "created_by": (uploaded_by or None) if owner is None else None,
    }
    # Count before paging, not after. A page requested past the end (reloading
    # after deleting the last row on that page, or a stale ?page= link) must be
    # clamped — otherwise the client gets an empty `files` list with a nonzero
    # `total`, which satisfies neither the "no results" empty state nor the
    # "more than one page" pager condition and renders a blank table. Asking
    # for the rows first meant fetching, and throwing away, a page nobody would
    # ever see; the total is what decides which page to fetch, so it goes first.
    total = await service.count_files(**filters)
    page = clamp_page(params.page, total, _PER_PAGE)
    items = await service.page_of_files(page=page, per_page=_PER_PAGE, **filters)
    # The bucket-wide numbers — usage and both facet lists — come from one
    # scan, cached only for legacy manager visibility. They ignore search filters so the
    # dropdowns keep offering the other types and people (a filter that hides
    # its own alternatives is a dead end) and so the usage figure keeps
    # describing the bucket rather than the search box.
    aggregates = await service.storage_aggregates()
    content_types = [facet.as_dict() for facet in aggregates.content_types]
    uploaders: list[dict] = [{"id": f.value, "count": f.count} for f in aggregates.uploaders]
    # One lookup covers the rows on screen and the filter's options, so
    # picking someone from the dropdown never renames them.
    labels = await resolve_uploader_labels(
        get_user_directory(request.app),
        db,
        [item.uploaded_by for item in items] + [u["id"] for u in uploaders],
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
            # tenant get it; others see usage of visible files, with no ceiling.
            "used_bytes": aggregates.used_bytes,
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


def _file_payload(item: StoredFileOut, labels: dict[str, str]) -> dict:
    """One row, with its uploader resolved to something readable."""
    payload = item.model_dump(mode="json")
    payload["uploaded_by_label"] = label_for(item.uploaded_by, labels)
    return payload
