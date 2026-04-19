"""Inertia view endpoints for the file_storage module."""

from __future__ import annotations

from fastapi import APIRouter, Depends
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
    page: int = 1,
    service: FileStorageService = Depends(get_file_storage_service),
) -> InertiaResponse:
    items, total = await service.list_files(page=page, per_page=_PER_PAGE)
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
        },
    )
