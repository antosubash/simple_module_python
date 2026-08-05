"""Site-wide password gate.

Runs outermost among module middleware — the module sorts after ``Auth``, and
Starlette's ``add_middleware`` is LIFO — so this executes *before*
``AuthMiddleware``. That ordering is the whole point: an anonymous visitor
sees the gate instead of being redirected to the login page, so a locked site
never reveals that a login form exists.

``SessionMiddleware`` sits outside this one, so ``scope["session"]`` is
readable here and writes are persisted on the way out.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.types import ASGIApp, Receive, Scope, Send

from site_lock import constants as c
from site_lock.page import render_unlock_page, safe_next

logger = logging.getLogger(__name__)

_NO_STORE = {"Cache-Control": "no-store"}
_ERR_WRONG = "Incorrect password."
_ERR_THROTTLED = "Too many attempts. Try again later."


def password_fingerprint(password: str) -> str:
    """Short digest of the active password, stored in the session.

    Comparing this on each request is what makes a password rotation
    invalidate every previously-unlocked session.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()[:16]


class SiteLockMiddleware:
    """Gate every request behind a single shared password."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        state = scope["app"].state.site_lock
        settings = state.settings

        # Default-off fast path: one attribute read, no Request construction.
        if not settings.enabled:
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        # Kubernetes probes must never be gated, or the pod gets killed.
        if path.startswith(c.HEALTH_PREFIX):
            await self.app(scope, receive, send)
            return

        fingerprint = password_fingerprint(settings.password)
        session = scope.get("session")

        if path == c.UNLOCK_PATH:
            response = await self._unlock(scope, receive, state, fingerprint, session)
            await response(scope, receive, send)
            return

        if session is not None and session.get(c.SESSION_KEY) == fingerprint:
            await self.app(scope, receive, send)
            return

        if await self._is_admin(scope):
            # Stamp the marker so the provider lookup costs once per session
            # rather than once per request.
            if session is not None:
                session[c.SESSION_KEY] = fingerprint
            await self.app(scope, receive, send)
            return

        await self._gate(scope, receive, send, path)

    async def _gate(self, scope: Scope, receive: Receive, send: Send, path: str) -> None:
        has_auth_header = any(k == b"authorization" for k, _ in scope.get("headers", ()))
        if path.startswith(c.API_PREFIX) or has_auth_header:
            # 403 rather than 401: a 401 would invite an auth flow that cannot
            # succeed while the site is locked.
            response: Response = JSONResponse(
                {"detail": "Site is locked"}, status_code=403, headers=_NO_STORE
            )
        else:
            target = f"{c.UNLOCK_PATH}?next={quote(safe_next(path), safe='/')}"
            response = RedirectResponse(target, status_code=302, headers=_NO_STORE)
        await response(scope, receive, send)

    async def _unlock(
        self,
        scope: Scope,
        receive: Receive,
        state,
        fingerprint: str,
        session,
    ) -> Response:
        method: str = scope.get("method", "GET")
        settings = state.settings
        request = Request(scope, receive)

        if method == "GET":
            return HTMLResponse(
                render_unlock_page(
                    message=settings.message,
                    next_url=request.query_params.get("next", "/"),
                ),
                headers=_NO_STORE,
            )
        if method != "POST":
            return Response(status_code=405, headers=_NO_STORE)

        client = scope.get("client")
        key = client[0] if client else "unknown"
        if state.limiter.is_blocked(key):
            return self._page(settings, _ERR_THROTTLED, "/", status=429)

        form = await request.form()
        supplied = str(form.get("password", ""))
        target = safe_next(str(form.get("next", "/")))

        if secrets.compare_digest(supplied, settings.password):
            state.limiter.reset(key)
            if session is not None:
                session[c.SESSION_KEY] = fingerprint
            return RedirectResponse(target, status_code=303, headers=_NO_STORE)

        state.limiter.record_failure(key)
        return self._page(settings, _ERR_WRONG, target, status=401)

    @staticmethod
    def _page(settings, error: str, next_url: str, *, status: int) -> HTMLResponse:
        return HTMLResponse(
            render_unlock_page(message=settings.message, error=error, next_url=next_url),
            status_code=status,
            headers=_NO_STORE,
        )

    @staticmethod
    async def _is_admin(scope: Scope) -> bool:
        """True when the caller already holds a session for an admin user.

        This is the documented lockout escape hatch: an admin who enables the
        gate and mistypes the password keeps access to the settings screen.
        """
        auth_state = getattr(scope["app"].state, "auth", None)
        provider = getattr(auth_state, "auth_provider", None)
        if provider is None:
            return False
        try:
            user = await provider.resolve_user(Request(scope))
        except Exception:
            logger.exception("Site lock admin bypass failed; treating as anonymous")
            return False
        return user is not None and c.ADMIN_ROLE in getattr(user, "roles", ())


__all__ = ["SiteLockMiddleware", "password_fingerprint"]
