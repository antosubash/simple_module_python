"""Configured and allowlisted origins for public links."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_address

from simple_module_core.modules.app_state import get_host_services
from starlette.requests import Request

from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._forwarded_host import TRUSTED_PROXY_SCOPE_KEY, HostAllowlist

__all__ = ["public_origin", "trusted_request_origin"]


def public_origin(settings: HostSettings | None, override: str = "") -> str:
    """Explicit module origin → host origin → relative links (fresh installs)."""
    return (override.strip() or (settings.public_base_url if settings else "")).rstrip("/")


@lru_cache(maxsize=16)
def _allowlist(entries: tuple[str, ...]) -> HostAllowlist:
    return HostAllowlist(entries)


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host.removeprefix("[").removesuffix("]")).is_loopback
    except ValueError:
        return False


def trusted_request_origin(request: Request) -> str | None:
    """Accept an allowlisted HTTP(S) authority from the resolved request scope."""
    settings = getattr(get_host_services(request.app), "settings", None)
    scheme = request.scope.get("scheme")
    if not settings or not settings.forwarded_host_allowlist or scheme not in ("http", "https"):
        return None

    authority = request.url.netloc
    # Starlette can fall back to scope["server"] for a malformed Host. A supplied
    # authority must be the one that actually resolved, and it must be unambiguous.
    host_headers = request.headers.getlist("host")
    if host_headers and host_headers != [authority]:
        return None
    parsed = _allowlist(tuple(settings.forwarded_host_allowlist)).match(authority)
    if parsed is None:
        return None
    host, port = parsed
    if scheme == "http" and not (request.scope.get(TRUSTED_PROXY_SCOPE_KEY) or _is_loopback(host)):
        return None
    return f"{scheme}://{host}" if port is None else f"{scheme}://{host}:{port}"
