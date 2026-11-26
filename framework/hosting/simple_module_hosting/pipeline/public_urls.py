"""Configured and allowlisted origins for public links."""

from __future__ import annotations

from functools import lru_cache

from simple_module_core.modules.app_state import get_host_services
from starlette.datastructures import URL
from starlette.requests import Request

from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline._forwarded_host import TRUSTED_PROXY_SCOPE_KEY, HostAllowlist
from simple_module_hosting.pipeline._insecure_transport import _is_loopback

__all__ = ["public_origin", "trusted_request_origin"]


def public_origin(settings: HostSettings | None, override: str = "") -> str:
    """Explicit module origin → host origin → relative links (fresh installs)."""
    return (override.strip() or (settings.public_base_url if settings else "")).rstrip("/")


@lru_cache(maxsize=16)
def _allowlist(entries: tuple[str, ...]) -> HostAllowlist:
    return HostAllowlist(entries)


def trusted_request_origin(request: Request) -> str | None:
    """Accept an allowlisted HTTP(S) authority from the resolved request scope."""
    settings = getattr(get_host_services(request.app), "settings", None)
    scheme = request.scope.get("scheme")
    if not settings or not settings.forwarded_host_allowlist or scheme not in ("http", "https"):
        return None

    # Use the authority after proxy handling without interpreting the path or query.
    host_headers = request.headers.getlist("host")
    if len(host_headers) == 1:
        (authority,) = host_headers
        if authority != authority.strip():
            return None
    elif not host_headers:
        authority = URL(scope={**request.scope, "path": "/", "query_string": b""}).netloc
    else:
        return None
    parsed = _allowlist(tuple(settings.forwarded_host_allowlist)).match(authority)
    if parsed is None:
        return None
    host, port = parsed
    if scheme == "http" and not (
        request.scope.get(TRUSTED_PROXY_SCOPE_KEY) or _is_loopback(host.strip("[]"))
    ):
        return None
    return f"{scheme}://{host}" if port is None else f"{scheme}://{host}:{port}"
