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
        # None when unset, so the frontend keeps the framework's own
        # `© {year} · MIT` caption rather than rendering a blank line.
        "footerText": settings.footer_text or None,
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


_NO_PAGE_PREFIXES = ("/api/", "/static/")


def renders_a_page(request: Request) -> bool:
    """Whether ``request`` can render an Inertia page (or the HTML shell).

    Providers run on every request, API and static ones included; resolving a
    tenant's branding there is a cache lookup — or a DB read on a miss — for a
    prop nobody reads. The same path rule the error handlers use: nothing under
    ``/api/`` or ``/static/`` is a page (Inertia views never live under
    ``/api/``, SM018). Elsewhere an Inertia visit, or anything a browser could
    be navigating with (``text/html``, ``*/*``, or no ``Accept``), counts.
    """
    if request.headers.get("x-inertia"):
        return True
    path = request.url.path
    if path == "/api" or path.startswith(_NO_PAGE_PREFIXES):
        return False
    accept = request.headers.get("accept", "")
    return not accept or "text/html" in accept or "*/*" in accept


async def branding_shared_props(request: Request) -> dict:
    """Provider: emit ``{"branding": {...}}`` for the request's tenant (#373).

    The system theme when ``multi_tenant`` is off or no tenant is bound — the
    process-wide object, with no lookup. For a tenant, its overrides on top
    (``tenant_branding.resolve``), which are also left on
    ``request.state.branding`` so the root template's pre-hydration ``<head>``
    (title, theme colour, favicon) matches the page.

    Defensive — returns ``{}`` if the branding state isn't mounted yet, so a
    half-booted app never errors a page render.
    """
    from branding.services import BrandingServices
    from branding.tenant_branding import resolve

    if getattr(request.app.state, "branding", None) is None or not renders_a_page(request):
        return {}
    resolved = await resolve(request)
    if resolved.tenant_fields:
        request.state.branding = BrandingServices(
            settings=resolved.settings, tenant_cache=request.app.state.branding.tenant_cache
        )
    return {"branding": branding_payload(resolved.settings)}
