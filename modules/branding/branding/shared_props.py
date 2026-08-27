"""Branding shared-props provider.

Registered on ``app.state.inertia_shared_providers`` so every Inertia page
(authenticated *and* guest) receives a ``branding`` block in its shared props.
The frontend uses it for the app name, logo, favicon and primary colour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from branding.constants import (
    ASSET_VERSION_QUERY_KEY,
    FAVICON_URL,
    LOGO_DARK_URL,
    LOGO_URL,
)

if TYPE_CHECKING:
    from starlette.requests import Request

    from branding.settings import BrandingSettings


def asset_url(base: str, file_id: str) -> str | None:
    """Version a public branding asset URL with the stored file id (or None).

    Points at branding's own anonymous route rather than file_storage's
    permission-gated download, so the image also loads for a logged-out
    visitor. Replacing an image stores a *new* file, so the id doubles as a
    content-address: the URL changes, and caches invalidate for free.
    """
    return f"{base}?{ASSET_VERSION_QUERY_KEY}={file_id}" if file_id else None


def branding_payload(settings: BrandingSettings) -> dict:
    """The camelCase branding block shared with the frontend."""
    return {
        "appName": settings.app_name,
        "primaryColor": settings.primary_color or None,
        "designPack": settings.design_pack or None,
        "logoUrl": asset_url(LOGO_URL, settings.logo_file_id),
        # None when unset — the frontend falls back to ``logoUrl``, so a
        # deployment with a single logo keeps its current appearance.
        "logoDarkUrl": asset_url(LOGO_DARK_URL, settings.logo_dark_file_id),
        "faviconUrl": asset_url(FAVICON_URL, settings.favicon_file_id),
        # None when the admin hasn't set any, so the frontend falls back to the
        # framework's own BRAND_FOOTER_LINKS rather than rendering an empty row.
        "footerLinks": (
            [{"label": link.label, "href": link.href} for link in settings.footer_links] or None
        ),
        # None when no message is set, so the frontend renders nothing at all
        # rather than an empty bar.
        "banner": (
            {"message": settings.banner_message, "severity": settings.banner_severity}
            if settings.banner_message
            else None
        ),
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
