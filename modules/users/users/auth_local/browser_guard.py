"""Session-bound validation for browser auth mutations."""

from fastapi import Request
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf, require_browser_origin

__all__ = ["require_browser_csrf", "require_browser_origin"]


async def require_browser_csrf(request: Request) -> None:
    """Native clients omit browser headers; browsers echo their page's token."""
    await require_browser_origin(request)
    if any(
        name in request.headers for name in ("origin", "referer", "sec-fetch-site", CSRF_HEADER)
    ):
        await RequiresCsrf()(request)
