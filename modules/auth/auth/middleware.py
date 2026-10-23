"""Provider-agnostic authentication middleware.

Delegates user resolution to the ``AuthProvider`` registered on
``app.state.auth.auth_provider``, then falls through to the
principal-resolver chain. Sets ``request.state.user`` and the
``current_user_id`` ContextVar for audit listeners.
"""

from __future__ import annotations

import logging

from simple_module_core.app_state import get_openapi_url
from simple_module_core.redirect_safety import SESSION_NEXT_KEY, safe_next_or_none
from simple_module_db.listeners import current_user_id
from simple_module_hosting.public_access import is_public as route_is_public
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from auth._route_match import route_exists

logger = logging.getLogger(__name__)

_FRAMEWORK_PUBLIC_PREFIXES = (
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/i18n/",
)
_FRAMEWORK_PUBLIC_EXACT = ("/",)


def _query_suffix(request: Request) -> str:
    return f"?{request.url.query}" if request.url.query else ""


def _is_navigation(request: Request) -> bool:
    """Whether this request is the page the visitor asked for, not something it loaded.

    Only a navigation may become the post-login target: the sign-in page's
    own favicon request used to overwrite it, so sign-in landed on
    /favicon.ico (#416). Inertia visits count — a session expiring mid-click
    must still return the user to that page. Without fetch metadata (old
    clients, scripts) keep the previous behaviour.
    """
    headers = request.headers
    if headers.get("x-inertia") == "true":
        return True
    dest = headers.get("sec-fetch-dest")
    if dest is not None:
        return dest == "document"
    mode = headers.get("sec-fetch-mode")
    if mode is not None:
        return mode == "navigate"
    return True


class AuthMiddleware:
    """Authenticate requests via the registered AuthProvider.

    On cache miss (provider returns None), falls through to the
    principal-resolver chain. Unauthenticated API requests get 401 JSON;
    unauthenticated browser requests get a redirect to the provider's
    login URL.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        method: str = scope.get("method", "GET")
        app_state = scope["app"].state
        auth_state = app_state.auth
        provider = auth_state.auth_provider

        if provider is None:
            await self.app(scope, receive, send)
            return

        is_public = (
            any(path.startswith(p) for p in _FRAMEWORK_PUBLIC_PREFIXES)
            or path in _FRAMEWORK_PUBLIC_EXACT
            # Anonymous exactly when the host serves it (dev, or openapi_public).
            or path == get_openapi_url(scope["app"])
        )
        if not is_public:
            is_public = route_is_public(scope["app"], method, path)

        # Contract with the host's RateLimitMiddleware (plain scope key, no import
        # between them): whether *this* middleware treats the request as anonymous-
        # allowed, from all three sources above. One source of truth.
        scope.setdefault("state", {})["auth_public"] = is_public

        request = Request(scope)
        user_ctx = await provider.resolve_user(request)

        if user_ctx is None:
            for resolver in auth_state.principal_resolvers:
                try:
                    user_ctx = await resolver(request)
                except Exception:
                    logger.exception(
                        "Principal resolver %r raised; treating as no-match",
                        resolver,
                    )
                    continue
                if user_ctx is not None:
                    break

        if user_ctx is None and not is_public and not route_exists(scope):
            # Nothing would serve this path (#473): let the app's 404 answer it
            # — the same page a signed-in caller gets — rather than sending the
            # visitor to sign in for a page that does not exist, or keeping it
            # as their post-login target. The request now reaches the app
            # anonymously, so the rate limiter treats it like any public hit.
            scope["state"]["auth_public"] = True
            is_public = True

        if user_ctx is None and not is_public:
            if path.startswith("/api/") or provider.is_bearer_request(request):
                response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            else:
                # Stash where they were heading so the login flow can return
                # them there. Relative, not ``str(request.url)``: the value is
                # replayed into a ``Location`` header, and an absolute URL is
                # both needless and an open-redirect shape. ``next_url`` also
                # goes to the provider — session-based providers ignore it,
                # but a redirect-based one (OIDC) needs it in the auth URL.
                session = scope.get("session", {})
                # Only a navigation is a target: a subresource (the sign-in
                # page's own favicon) would overwrite it (#416).
                next_url = (
                    safe_next_or_none(request.url.path + _query_suffix(request))
                    if _is_navigation(request)
                    else None
                )
                if next_url is not None:
                    session[SESSION_NEXT_KEY] = next_url
                response = RedirectResponse(
                    provider.get_login_url(request, next_url), status_code=302
                )
            await response(scope, receive, send)
            return

        if user_ctx is not None:
            request.state.user = user_ctx
            for guard in auth_state.principal_guards:
                refusal = guard(request)
                if refusal is not None:
                    await refusal(scope, receive, send)
                    return
            token = current_user_id.set(user_ctx.id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
            return

        await self.app(scope, receive, send)


__all__ = ["AuthMiddleware"]
