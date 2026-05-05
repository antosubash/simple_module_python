"""Inertia view endpoints for the LacoWiki migration wireframes."""

from __future__ import annotations

from fastapi import APIRouter
from inertia import InertiaResponse
from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/", response_model=None)
async def home(inertia: InertiaDep) -> InertiaResponse:
    """Wireframes browser — Overview / Design system / Wireframes tabs."""
    return await inertia.render("LacoWiki/Home", {})


@router.get("/datasets", response_model=None)
async def datasets(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Datasets", {})


@router.get("/legends", response_model=None)
async def legends(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Legends", {})


@router.get("/sampling", response_model=None)
async def sampling(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Sampling", {})


@router.get("/validation", response_model=None)
async def validation(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Validation", {})


@router.get("/reports", response_model=None)
async def reports(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Reports", {})


@router.get("/account", response_model=None)
async def account(inertia: InertiaDep) -> InertiaResponse:
    return await inertia.render("LacoWiki/Account", {})
