"""Session-bound validation for browser auth mutations."""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from simple_module_hosting.csrf import CSRF_HEADER, RequiresCsrf


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise ValueError("Invalid origin")
    return (
        parsed.scheme,
        parsed.hostname,
        parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80),
    )


async def require_browser_origin(request: Request) -> None:
    """Refuse browser mutations initiated by a foreign origin."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    source = request.headers.get("origin") or request.headers.get("referer")
    site = request.headers.get("sec-fetch-site")
    try:
        foreign = source is not None and _origin(source) != _origin(str(request.base_url))
    except ValueError:
        foreign = True
    if foreign or site == "cross-site":
        raise HTTPException(status_code=403, detail="Browser request source refused")


async def require_browser_csrf(request: Request) -> None:
    """Native clients omit browser headers; browsers echo their page's token."""
    await require_browser_origin(request)
    if (
        any(name in request.headers for name in ("origin", "referer", "sec-fetch-site"))
        or CSRF_HEADER in request.headers
    ):
        await RequiresCsrf()(request)
