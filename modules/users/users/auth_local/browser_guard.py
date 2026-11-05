"""Session-bound validation for browser auth mutations."""

from fastapi import HTTPException, Request
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf


async def require_browser_origin(request: Request) -> None:
    """Refuse browser mutations the browser itself labels ``cross-site``.

    Origin/Referer are deliberately not compared with ``request.base_url``: behind
    a TLS-terminating proxy without trusted-proxy handling the app sees
    ``http://internal`` while the browser sends ``https://app.example``, which
    would refuse every sign-in and sign-out. Login CSRF is stopped by the session
    CSRF token (``require_browser_csrf``); this check adds the fetch-metadata
    refusal for browsers that send it.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Browser request source refused")


async def require_browser_csrf(request: Request) -> None:
    """Native clients omit browser headers; browsers echo their page's token."""
    await require_browser_origin(request)
    if any(
        name in request.headers for name in ("origin", "referer", "sec-fetch-site", CSRF_HEADER)
    ):
        await RequiresCsrf()(request)
