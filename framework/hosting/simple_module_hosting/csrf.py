"""CSRF protection middleware.

Validates a per-session token on state-changing requests. The token is minted
once per session by :class:`InertiaLayoutDataMiddleware` and embedded in the
Inertia shared props as ``csrf_token``; the frontend echoes it back in the
``X-CSRF-Token`` (or ``X-XSRF-Token``) header on every non-safe request.

Installed *after* ``SessionMiddleware`` so ``scope["session"]`` is populated.
"""

from __future__ import annotations

import logging
import secrets

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

SESSION_CSRF_TOKEN_KEY = "csrf_token"
"""Session-dict key under which :class:`InertiaLayoutDataMiddleware` mints
the per-session CSRF token that :class:`CSRFMiddleware` validates."""

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_HEADER_NAMES = ("x-csrf-token", "x-xsrf-token")


class CSRFMiddleware:
    """Reject unsafe-method requests without a valid session-bound CSRF token.

    ``exempt_path_prefixes`` opts specific path prefixes out of the check —
    use sparingly, only for endpoints that genuinely cannot carry a session
    (e.g. webhook receivers authenticated by signature).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_path_prefixes: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.exempt_path_prefixes = exempt_path_prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        if method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if any(path.startswith(p) for p in self.exempt_path_prefixes):
            await self.app(scope, receive, send)
            return

        session = scope.get("session")
        expected = session.get(SESSION_CSRF_TOKEN_KEY) if session is not None else None

        headers = Headers(scope=scope)
        provided = ""
        for name in _HEADER_NAMES:
            value = headers.get(name)
            if value:
                provided = value
                break

        if not expected or not provided or not secrets.compare_digest(str(expected), provided):
            logger.info(
                "csrf.rejected",
                extra={"method": method, "path": path, "has_token": bool(expected)},
            )
            response = PlainTextResponse("CSRF validation failed", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
