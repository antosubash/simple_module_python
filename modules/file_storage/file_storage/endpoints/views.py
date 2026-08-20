"""Inertia view endpoints for the file_storage module."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission

from file_storage import constants
from file_storage.deps import get_file_storage_service
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
    service: FileStorageService = Depends(get_file_storage_service),
) -> InertiaResponse:
    # A user-supplied page below 1 (0, negative, a hand-edited ?page=) must
    # clamp to the first page rather than reject — mirrors the past-the-end
    # clamp below so no value of ?page= can produce a raw validation-error
    # page for a browser-facing route.
    page = max(page, 1)
    items, total = await service.list_files(
        page=page,
        per_page=_PER_PAGE,
        search=q or None,
        content_type=content_type or None,
    )
    # A page requested past the end (e.g. reloading after deleting the last
    # row on that page, or a stale ?page= link) must be clamped and
    # re-queried — otherwise the client gets an empty `files` list with a
    # nonzero `total`, which satisfies neither the "no results" empty state
    # nor the "more than one page" pager condition and renders a blank table.
    total_pages = max(1, math.ceil(total / _PER_PAGE))
    if page > total_pages:
        page = total_pages
        items, total = await service.list_files(
            page=page,
            per_page=_PER_PAGE,
            search=q or None,
            content_type=content_type or None,
        )
    # Facets ignore the active filters so the dropdown keeps offering the
    # other types — a filter that hides its own alternatives is a dead end.
    facets = await service.content_type_facets()
    # The page name is hard-coded as a literal here (rather than via
    # ``constants.PAGE_BROWSE``) so the SM003/SM004 diagnostics — which do
    # static AST analysis and cannot resolve attribute access — pair this
    # call with ``pages/Browse.tsx``. A unit test asserts the literal
    # matches ``constants.PAGE_BROWSE``.
    return await inertia.render(
        "FileStorage/Browse",
        {
            "files": [item.model_dump(mode="json") for item in items],
            "pagination": {"page": page, "perPage": _PER_PAGE, "total": total},
            "filters": {"q": q, "content_type": content_type},
            "content_types": facets,
        },
    )
