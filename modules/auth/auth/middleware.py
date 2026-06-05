"""Provider-agnostic authentication middleware.

Delegates user resolution to the ``AuthProvider`` registered on
``app.state.auth.auth_provider``, then falls through to the
principal-resolver chain. Sets ``request.state.user`` and the
``current_user_id`` ContextVar for audit listeners.
"""

from __future__ import annotations

import logging

from simple_module_db.listeners import current_user_id
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_FRAMEWORK_PUBLIC_PREFIXES = (
    "/health",
    "/static/",
    "/api/docs",
    "/api/redoc",
    "/openapi.json",
    "/i18n/",
)
_FRAMEWORK_PUBLIC_EXACT = ("/",)
_SESSION_NEXT_KEY = "next"


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
        )
        # Module-contributed public routes (register_public_routes hook). Method
        # -aware, so a GET read route can be exempted without opening sibling
        # POST/PATCH mutations under the same prefix.
        if not is_public:
            public_routes = getattr(app_state, "public_routes", None)
            is_public = public_routes is not None and public_routes.matches(method, path)
        # Legacy provider-declared paths (prefix-only, method-agnostic). Kept for
        # back-compat with AuthProvider implementations.
        if not is_public:
            prefix_paths, exact_paths = provider.get_public_paths()
            is_public = any(path.startswith(p) for p in prefix_paths) or path in exact_paths

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

        if user_ctx is None and not is_public:
            if path.startswith("/api/") or provider.is_bearer_request(request):
                response = JSONResponse({"detail": "Not authenticated"}, status_code=401)
            else:
                session = scope.get("session", {})
                session[_SESSION_NEXT_KEY] = str(request.url)
                response = RedirectResponse(provider.get_login_url(request), status_code=302)
            await response(scope, receive, send)
            return

        if user_ctx is not None:
            request.state.user = user_ctx
            token = current_user_id.set(user_ctx.id)
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
            return

        await self.app(scope, receive, send)


__all__ = ["AuthMiddleware"]
