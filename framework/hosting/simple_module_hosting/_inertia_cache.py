"""Keep the Inertia payload out of caches that answer page requests.

Every Inertia route serves one URL as two representations, chosen on the
request's ``X-Inertia`` header: an HTML document for a full page load, a JSON
payload for a client-side visit. Nothing in either response says so, which
leaves a cache free to store one and hand it back for the other. Visit a page
through the SPA, then open the same URL directly, and the browser can serve the
stored payload as the document — the visitor gets
``{"component":"...","props":{...}}`` where the page should be.

That only bites once a route marks itself cacheable, which a public-content
module reasonably does. The framework is what makes it unsafe:
:class:`~simple_module_hosting.middleware.InertiaLayoutDataMiddleware` merges
the signed-in user's ``auth`` block, their permission list and the menus their
roles resolve to into *every* Inertia payload. A route author choosing
``Cache-Control: public`` for their page content has no way to know that, so
the guarantee belongs here rather than in each module:

* **An Inertia payload is never stored.** ``private, no-store``, and the ETag
  is dropped so no cache can revalidate its way back to a copy it should not
  have kept. The cost is per-visit caching on client-side navigation, which was
  never safe to take — those bytes are specific to one user.
* **Both representations declare ``Vary: X-Inertia``**, so a cache that honours
  Vary keeps them in separate entries instead of inferring it from ``Accept``.

``Vary`` is added to the document only when the response is HTML, so static
assets and JSON APIs keep the validators and cache entries they had.

A module that wants its public page content cached should give the *document*
its own ``Cache-Control`` and an ETag that identifies the representation; this
middleware leaves that path alone and only governs the payload.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_SCOPE_HTTP = "http"
_HEADER_INERTIA = b"x-inertia"

#: What an Inertia payload is allowed to say about its own cacheability.
PAYLOAD_CACHE_CONTROL = "private, no-store"

#: The request header that selects the representation, and therefore the one
#: caches must key on.
VARY_FIELD = "X-Inertia"


def add_vary(headers: MutableHeaders, field: str = VARY_FIELD) -> None:
    """Add a field to ``Vary``, keeping whatever is already listed."""
    existing = headers.get("vary")
    if not existing:
        headers["vary"] = field
        return
    if any(part.strip().lower() == field.lower() for part in existing.split(",")):
        return
    headers["vary"] = f"{existing}, {field}"


def is_inertia_request(scope: Scope) -> bool:
    """Whether this request asked for the JSON representation.

    Mirrors ``fastapi-inertia``'s own ``Inertia._is_inertia_request`` exactly —
    presence of the header, any value — rather than requiring it to equal
    ``"true"``. The library renders JSON for *any* ``X-Inertia`` value, so a
    stricter check here would disagree with it: a request the renderer treats
    as Inertia would sail through uncached, undoing the whole fix.
    """
    return any(key == _HEADER_INERTIA for key, _ in scope.get("headers", ()))


def _is_html(headers: MutableHeaders) -> bool:
    return headers.get("content-type", "").split(";", 1)[0].strip() == "text/html"


class InertiaCacheMiddleware:
    """Stop an Inertia payload being cached as though it were the page."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != _SCOPE_HTTP:
            await self.app(scope, receive, send)
            return

        inertia = is_inertia_request(scope)

        async def send_with_cache_rules(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if inertia:
                    headers["cache-control"] = PAYLOAD_CACHE_CONTROL
                    del headers["etag"]
                    add_vary(headers)
                elif _is_html(headers):
                    add_vary(headers)
            await send(message)

        await self.app(scope, receive, send_with_cache_rules)


__all__ = ["PAYLOAD_CACHE_CONTROL", "VARY_FIELD", "InertiaCacheMiddleware", "add_vary"]
