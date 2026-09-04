"""Make Inertia's page ``url`` root-relative, as the protocol specifies.

``fastapi-inertia`` builds the page object with the *absolute* request url::

    page_data = {
        "component": self._component,
        "props": await self._build_props(),
        "url": str(self._request.url),      # http://host:8000/dashboard/
        "version": self._config.version,
    }

The Inertia protocol says otherwise — every official adapter emits a
root-relative path (Laravel's ``$request->getRequestUri()``, Rails'
``request.original_fullpath``), and the documented page object is
``{"component": "Event", "props": {...}, "url": "/events/80", ...}``. The
client hands that value straight to ``history.pushState``/``replaceState``,
which resolves a relative url against the current document and so can never
disagree with it.

An absolute url can, and behind a TLS-terminating reverse proxy it always
does. The proxy speaks https to the browser and http to the container, so
``request.url`` is ``http://…`` while the document origin is ``https://…``,
and the browser rejects the state write::

    SecurityError: Failed to execute 'pushState' on 'History': A history state
    object with URL 'http://example.com/' cannot be created in a document with
    origin 'https://example.com' and URL 'https://example.com/'

That fires on *every* page — the initial ``replaceState`` and every subsequent
visit — so history state is never written: back/forward navigation and scroll
restoration silently stop working, and the console fills with the error. The
throw escapes as an unhandled rejection, because the client's
``isHistoryThrottleError`` guard matches the string ``"history.pushState"``
while the browser's message reads ``"Failed to execute 'pushState'"``.

``SM_TRUSTED_PROXY`` fixes the scheme by trusting ``X-Forwarded-Proto``, and is
still worth setting — it is what makes request logs record the real client IP.
But an install should not need it merely to have working history, and trusting
forwarded headers is a security decision that must stay opt-in: the default
image is documented as runnable standalone, where a spoofed ``X-Forwarded-For``
would poison the audit log. Emitting the relative url the protocol asks for
removes the dependency entirely, whatever the deployment looks like.

Patched at ``_get_page_data`` because it is the single choke point: upstream's
SSR, JSON and full-page-load branches all build their payload from it. The
replacement binds to the instance, so the library's class is untouched.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def relative_page_url_dependency(inertia_dep: Any) -> Any:
    """Wrap an Inertia dependency so its page ``url`` is root-relative.

    Keeps the ``(request, client)`` shape ``inertia_dependency_factory``
    returns, and composes with the other wraps in either order — each patches a
    different instance attribute, and the JSON wrap looks ``_get_page_data`` up
    on the instance at call time.

    An instance that doesn't expose the hook is handed back untouched: the
    failure mode is the absolute url that already ships, and refusing to boot
    because an upstream attribute moved would be a worse trade.
    """

    def dependency(request: Any, client: Any = None) -> Any:
        inertia = inertia_dep(request, client)
        if hasattr(inertia, "_get_page_data"):
            inertia._get_page_data = _page_data_for(inertia)
        else:  # pragma: no cover - upstream layout changed
            logger.warning(
                "Inertia instance has no _get_page_data; the page url stays "
                "absolute and history writes will fail behind a TLS proxy"
            )
        return inertia

    return dependency


def _page_data_for(inertia: Any) -> Any:
    """Build the instance's replacement ``_get_page_data``."""
    stock = inertia._get_page_data

    async def _get_page_data() -> dict:
        page_data = await stock()
        url = page_data.get("url")
        if isinstance(url, str):
            page_data["url"] = to_relative_url(url)
        return page_data

    return _get_page_data


def to_relative_url(url: str) -> str:
    """Reduce an absolute url to the path-and-query the protocol wants.

    A url that is already relative is returned unchanged, so this is safe to
    apply twice and safe to apply to a payload upstream may one day fix.
    Anything unparseable is passed through rather than mangled — a wrong url is
    still better than a crash on the render path.
    """
    try:
        parts = urlsplit(url)
    except ValueError:  # pragma: no cover - urlsplit is near-total
        return url
    if not parts.scheme and not parts.netloc:
        return url
    relative = parts.path or "/"
    if parts.query:
        relative = f"{relative}?{parts.query}"
    return relative


__all__ = ["relative_page_url_dependency", "to_relative_url"]
