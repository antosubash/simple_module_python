"""Read-only enforcement for the shared demo account.

A demo account is a *published* credential: the sign-in page hands it to
whoever asks. Without this guard, hosting a showcase instance means publishing
write access to the settings editor, the user table and maintenance mode — so
``demo_read_only`` defaults to on and this is what implements it.

Why a middleware and not a dependency: the point is to cover every route in
every installed module, including ones written before demo mode existed. A
dependency covers only the routes that remember to declare it.

Why it reads the session rather than ``request.state.user``: module middleware
sorts by ``depends_on``, and ``users`` depends on ``Auth``, so this executes
*before* ``AuthMiddleware`` has resolved anyone. The session cookie is already
decoded by then (``Session`` sits outside every module's middleware), and it
carries both the stamp the demo endpoint writes and the user id — which is
what catches a visitor who signed in with a published demo password through
the ordinary form instead of the button.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from users.constants import SESSION_USER_ID_KEY
from users.demo import SESSION_DEMO_KEY

#: The error body the frontend matches on to show "this is a read-only demo".
DEMO_READ_ONLY_DETAIL = "DEMO_READ_ONLY"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

#: Writes a demo visitor must keep: leaving is not a mutation of the instance,
#: and a demo you cannot sign out of is a demo you cannot show twice.
_ALLOWED_PATHS = frozenset(
    {
        "/users/logout",
        "/api/users/auth/logout",
        "/api/users/auth/demo",
    }
)


def is_demo_session(scope: Scope, demo_user_id) -> bool:
    """Whether this request is carrying the demo account's session."""
    session = scope.get("session") or {}
    if session.get(SESSION_DEMO_KEY):
        return True
    if demo_user_id is None:
        return False
    return str(session.get(SESSION_USER_ID_KEY) or "") == str(demo_user_id)


def _refusal(scope: Scope) -> Response:
    """The response a blocked write gets.

    Inertia rejects a non-Inertia response by throwing up a modal with the raw
    body in it, which on a showcase instance reads as a crash. The protocol's
    own escape hatch is a 409 carrying ``X-Inertia-Location``: the client does
    a hard visit to that URL instead. Sending it back where it came from means
    the page simply re-renders unchanged, and the standing demo banner is what
    explains why. Plain ``fetch`` callers — which is how most of this app
    writes — get the 403 and can show the reason inline.
    """
    headers = Request(scope).headers
    if headers.get("x-inertia"):
        return Response(
            status_code=409,
            headers={"X-Inertia-Location": headers.get("referer") or "/"},
        )
    return JSONResponse({"detail": DEMO_READ_ONLY_DETAIL}, status_code=403)


class DemoReadOnlyMiddleware:
    """Refuse unsafe HTTP methods from the shared demo session."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET") in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        state = getattr(scope["app"].state, "users", None)
        settings = getattr(state, "settings", None)
        # ``demo_mode`` and ``demo_read_only`` are both live-editable, so they
        # are read per request rather than captured at construction.
        if (
            settings is None
            or not getattr(settings, "demo_mode", False)
            or not getattr(settings, "demo_read_only", True)
        ):
            await self.app(scope, receive, send)
            return

        if scope["path"] in _ALLOWED_PATHS:
            await self.app(scope, receive, send)
            return

        if not is_demo_session(scope, getattr(state, "demo_user_id", None)):
            await self.app(scope, receive, send)
            return

        await _refusal(scope)(scope, receive, send)
