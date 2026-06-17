"""Branding shared-props provider.

Registered on ``app.state.inertia_shared_providers`` so every Inertia page
(authenticated *and* guest) receives a ``branding`` block in its shared props.
The frontend uses it for the app name, logo, favicon and primary colour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from branding.constants import FILE_DOWNLOAD_URL

if TYPE_CHECKING:
    from starlette.requests import Request

    from branding.settings import BrandingSettings


def file_url(file_id: str) -> str | None:
    """Build the file_storage download URL for a stored file id (or None)."""
    return FILE_DOWNLOAD_URL.format(file_id=file_id) if file_id else None


def branding_payload(settings: BrandingSettings) -> dict:
    """The camelCase branding block shared with the frontend."""
    return {
        "appName": settings.app_name,
        "primaryColor": settings.primary_color or None,
        "logoUrl": file_url(settings.logo_file_id),
        "faviconUrl": file_url(settings.favicon_file_id),
    }


def branding_shared_props(request: Request) -> dict:
    """Provider: emit ``{"branding": {...}}`` from the live module settings.

    Defensive — returns ``{}`` if the branding state isn't mounted yet, so a
    half-booted app never errors a page render.
    """
    services = getattr(request.app.state, "branding", None)
    if services is None:
        return {}
    return {"branding": branding_payload(services.settings)}
