"""Keep the session out of anonymous public-file responses (#353).

Public files are served ``Cache-Control: public`` so a CDN or shared proxy can
hold them. Two headers the session layer adds would undo that:

* ``Set-Cookie: session=…`` — the layout middleware records the locale and
  i18n audience it served in the session on *every* request, so an anonymous
  fetch mints a fresh 14-day session cookie. A shared cache that stores the
  response would hand that cookie to every later visitor.
* ``Vary: Cookie`` — added whenever anything read the session, which splits
  the cache into one entry per visitor for bytes that do not depend on who
  asked (the handler never looks at the caller).

Nothing on these routes needs to *write* the session, so this middleware tells
the session layer that nothing touched it: when the response starts it clears
the session's ``accessed``/``modified`` flags, and Starlette's
``SessionMiddleware`` then emits neither header. Clearing the flags rather than
swapping in a throwaway session keeps it correct whatever order the module
middleware ends up in — an auth layer further out may already have read the
real session on the way in. Writes made while serving are simply not persisted;
a signed-in visitor's existing cookie is left exactly as it was.
"""

from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from file_storage import constants

PUBLIC_PATH_PATTERN = (
    rf"{re.escape(constants.ROUTE_PREFIX_API + constants.PUBLIC_SEGMENT)}/[^/]+(/[^/]+)?$"
)
"""The anonymous read routes: ``/public/{id}``, ``/{id}/{name}``, ``/{id}/thumbnail``."""

_PUBLIC_PATH = re.compile(PUBLIC_PATH_PATTERN)
_READ_METHODS = frozenset({"GET", "HEAD"})


class CookielessPublicFilesMiddleware:
    """Suppress session ``Set-Cookie`` / ``Vary: Cookie`` on public file reads."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") not in _READ_METHODS
            or _PUBLIC_PATH.match(scope.get("path", "")) is None
        ):
            await self.app(scope, receive, send)
            return

        async def send_untouched(message: Message) -> None:
            if message["type"] == "http.response.start":
                _forget_session_use(scope.get("session"))
            await send(message)

        await self.app(scope, receive, send_untouched)


def _forget_session_use(session: object) -> None:
    # Starlette's ``Session`` decides both headers from these two flags alone.
    for flag in ("accessed", "modified"):
        if hasattr(session, flag):
            setattr(session, flag, False)
