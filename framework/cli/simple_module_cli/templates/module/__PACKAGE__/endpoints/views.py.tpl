"""Inertia view endpoints for {{MODULE_NAME}} — mounted under ``/{{MODULE_SLUG}}``."""

from __future__ import annotations

from fastapi import APIRouter
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()

_PAGE_INDEX = "{{MODULE_NAME}}/Index"


@router.get("/", response_model=None)
async def index(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render(_PAGE_INDEX, {})
