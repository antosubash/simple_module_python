"""Inertia view endpoints for the Datasets module."""

from __future__ import annotations

from celery import Celery
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from inertia import InertiaResponse
from simple_module_core.events import EventBus
from simple_module_hosting.inertia_deps import InertiaDep
from simple_module_hosting.permissions import RequiresPermission
from starlette.responses import RedirectResponse

from datasets import constants
from datasets.contracts.events import DatasetDeleted
from datasets.contracts.schemas import DatasetUpdate
from datasets.deps import (
    get_celery,
    get_dataset_service,
    get_event_bus,
    get_max_upload_bytes,
)
from datasets.endpoints.api import perform_upload
from datasets.service import DatasetService

# Module-local Inertia page identifiers. These must be Name-only literal
# assignments (not attribute access against ``constants``) so the SM003
# orphan-page diagnostic can resolve them — see
# ``simple_module_core.diagnostics._module._iter_render_components``.
_PAGE_BROWSE = "Datasets/Browse"
_PAGE_CREATE = "Datasets/Create"
_PAGE_SHOW = "Datasets/Show"
_PAGE_EDIT = "Datasets/Edit"

router = APIRouter()


@router.get("/", response_model=None)
async def browse(
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    items = await service.get_all()
    return await inertia.render(
        _PAGE_BROWSE,
        {"datasets": [item.model_dump(mode="json") for item in items]},
    )


@router.get(
    "/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_UPLOAD))],
)
async def create_view(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_CREATE)


@router.post(
    "/",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_UPLOAD))],
)
async def upload_view(
    request: Request,
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=2000),
    kind: str | None = Form(default=None),
    file: UploadFile = File(...),
    service: DatasetService = Depends(get_dataset_service),
    bus: EventBus = Depends(get_event_bus),
    celery: Celery = Depends(get_celery),
    max_upload_bytes: int = Depends(get_max_upload_bytes),
) -> RedirectResponse:
    # Inertia's client-side router expects a redirect after POST. Return 303
    # so it re-issues a GET against the browse page, which replies with a
    # full Inertia response.
    await perform_upload(
        request, name, description, kind, file, service, bus, celery, max_upload_bytes
    )
    return RedirectResponse(constants.REDIRECT_BROWSE, status_code=303)


@router.get("/{dataset_id}", response_model=None)
async def show_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            _PAGE_BROWSE,
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render(_PAGE_SHOW, {"dataset": item.model_dump(mode="json")})


@router.get(
    "/{dataset_id}/edit",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_EDIT))],
)
async def edit_view(
    dataset_id: int,
    inertia: InertiaDep,
    service: DatasetService = Depends(get_dataset_service),
) -> InertiaResponse:
    item = await service.get_by_id(dataset_id)
    if item is None:
        return await inertia.render(
            _PAGE_BROWSE,
            {"datasets": [], "error": "Dataset not found"},
        )
    return await inertia.render(_PAGE_EDIT, {"dataset": item.model_dump(mode="json")})


@router.patch(
    "/{dataset_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_EDIT))],
)
async def update_view(
    dataset_id: int,
    data: DatasetUpdate,
    service: DatasetService = Depends(get_dataset_service),
) -> RedirectResponse:
    item = await service.update(dataset_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return RedirectResponse(constants.REDIRECT_BROWSE, status_code=303)


@router.delete(
    "/{dataset_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission(constants.PERM_DATASETS_DELETE))],
)
async def delete_view(
    dataset_id: int,
    service: DatasetService = Depends(get_dataset_service),
    bus: EventBus = Depends(get_event_bus),
) -> RedirectResponse:
    existing = await service.get_by_id(dataset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    await service.delete(dataset_id)
    await bus.publish(DatasetDeleted(dataset_id=dataset_id, slug=existing.slug))
    return RedirectResponse(constants.REDIRECT_BROWSE, status_code=303)
