"""Session cookie whose browser lifetime is decided per request.

Starlette's ``SessionMiddleware`` uses one number for two jobs: it is the
cookie's ``Max-Age`` *and* the age at which the signature stops verifying. A
"keep me signed in for 30 days" checkbox therefore cannot be honoured from an
endpoint — writing a 30-day cookie is pointless when the signer rejects it on
day 14, and the middleware has no per-request hook because it appends its own
``Set-Cookie`` after the response's.

Splitting the two numbers is what makes the choice expressible: the signature
window is the longest session the deployment will ever accept, and the cookie
window is how long *this* browser was asked to keep it. Ordinary sign-ins keep
the 14-day cookie they always had; only a request that opts in gets more, and
never more than the signature window.

The cost is stated plainly: a session cookie lifted off disk stays replayable
for the signature window, not the cookie window. That is the price of the
checkbox. Revocation does not depend on either — the users provider re-reads
the account (and its ``session_version``) on every request.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from starlette.middleware.sessions import SessionMiddleware as _StarletteSessionMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_SIGNATURE_MAX_AGE = 30 * 24 * 60 * 60
"""Oldest session signature still accepted. The ceiling on "keep me signed in"."""

SESSION_COOKIE_MAX_AGE = 14 * 24 * 60 * 60
"""How long a browser is asked to keep the cookie when nothing opts in."""

SESSION_REMEMBER_KEY = "remember"
"""Session key holding the window this session was signed in for.

The source of truth, and it has to live *in the session* rather than on one
request's scope. Starlette re-emits the cookie on every response that modified
the session — which is most of them, since resolving the signed-in user caches
its context there — so a widened window recorded only on the sign-in response
would be quietly rolled back to the default by the very next page load.

Written as the number of seconds, so an operator who shortens the window gets
it honoured on every response rather than only on the first. ``True`` is
accepted too and means :data:`SESSION_SIGNATURE_MAX_AGE`.
"""

SESSION_COOKIE_MAX_AGE_KEY = "session_cookie_max_age"
"""ASGI scope key an endpoint sets to widen *this* response's cookie window.

``request.scope[SESSION_COOKIE_MAX_AGE_KEY] = seconds`` before returning. For
one response only — use :data:`SESSION_REMEMBER_KEY` for a window that has to
survive the next request. Values above :data:`SESSION_SIGNATURE_MAX_AGE` are
clamped in both cases: a cookie the signer will not accept is worse than a
shorter one, because it fails at the end of a long absence rather than at
sign-in.
"""

_MAX_AGE = re.compile(rb"Max-Age=\d+")


class SessionMiddleware(_StarletteSessionMiddleware):
    """``SessionMiddleware`` with the cookie window separated from the signature window."""

    def __init__(self, app: ASGIApp, secret_key: Any, **kwargs: Any) -> None:
        # The parent's ``max_age`` is what the signer verifies against, so it
        # takes the longer of the two. The cookie's own Max-Age is rewritten
        # on the way out.
        kwargs.pop("max_age", None)
        super().__init__(app, secret_key, max_age=SESSION_SIGNATURE_MAX_AGE, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        async def send_with_cookie_window(message: Message) -> None:
            if message["type"] == "http.response.start":
                _retime_session_cookie(message, self.session_cookie, _window(scope))
            await send(message)

        # Delegates every decision about *whether* to write a cookie to the
        # parent; this only edits the one it wrote.
        await super().__call__(scope, receive, send_with_cookie_window)


def _window(scope: Scope) -> int:
    """How long to ask the browser to keep the cookie about to be written.

    The session's own record wins: it is the only input that outlives the
    request that set it, so it is what keeps a remembered session remembered
    across every later response. The scope key is the one-response escape
    hatch, for callers that want to widen a cookie without recording anything.
    """
    remembered = _remembered_window(scope.get("session"))
    if remembered is not None:
        return remembered
    return _clamp(scope.get(SESSION_COOKIE_MAX_AGE_KEY))


def _remembered_window(session: Any) -> int | None:
    """The window recorded in the session, or ``None`` if it recorded none."""
    if not isinstance(session, Mapping):
        return None
    recorded = session.get(SESSION_REMEMBER_KEY)
    if recorded is True:
        return SESSION_SIGNATURE_MAX_AGE
    # ``bool`` is an ``int``: False must read as "not remembered" rather than
    # as a zero-second window.
    if isinstance(recorded, bool) or not isinstance(recorded, int):
        return None
    return _clamp(recorded)


def _clamp(seconds: Any) -> int:
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        return SESSION_COOKIE_MAX_AGE
    return min(seconds, SESSION_SIGNATURE_MAX_AGE)


def _retime_session_cookie(message: Message, cookie_name: str, max_age: int) -> None:
    """Rewrite ``Max-Age`` on the session ``Set-Cookie`` the parent just wrote.

    Leaves every other cookie alone, and leaves the session *clearing* header
    alone too — that one carries an ``expires`` in the past and no ``Max-Age``,
    so the pattern simply does not match it.
    """
    headers: list[Any] = message.get("headers") or []
    prefix = f"{cookie_name}=".encode()
    replacement = f"Max-Age={max_age}".encode()
    for index, (key, value) in enumerate(headers):
        if key.lower() == b"set-cookie" and value.startswith(prefix):
            headers[index] = (key, _MAX_AGE.sub(replacement, value, count=1))
