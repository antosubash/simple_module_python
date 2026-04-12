"""Inertia view endpoints for the Dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Request
from inertia import InertiaResponse

from simple_module_hosting.inertia_deps import InertiaDep

router = APIRouter()


@router.get("/", response_model=None)
async def landing(request: Request, inertia: InertiaDep) -> InertiaResponse:
    """Public landing page — no auth required."""
    is_authenticated = bool(request.session.get("userinfo"))
    return await inertia.render("Dashboard/Landing", {
        "isAuthenticated": is_authenticated,
    })


@router.get("/dashboard", response_model=None)
async def dashboard(inertia: InertiaDep) -> InertiaResponse:
    """Authenticated dashboard — requires login."""
    return await inertia.render("Dashboard/Home", {
        "welcome": "Welcome to SimpleModule",
    })
