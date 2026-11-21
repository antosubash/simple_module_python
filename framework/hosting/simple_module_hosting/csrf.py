"""Opt-in session-bound CSRF protection for module mutation endpoints.

The framework's baseline CSRF defence is ``SameSite=Lax`` on the session
cookie: browsers don't attach it to cross-site POSTs, so a forged form
submit arrives unauthenticated. Modules that want defence in depth (or must
satisfy a stricter audit) opt into a token check per router::

    from simple_module_hosting.csrf import RequiresCsrf

    router = APIRouter(dependencies=[Depends(RequiresCsrf())])

Signed-in Inertia pages share ``csrfToken`` automatically, including partial
reloads. The generated API client sends its current value as ``X-CSRF-Token``
on same-origin POST/PUT/PATCH/DELETE; page code needs no token plumbing.
Safe methods are never checked. Apps that mount no ``SessionMiddleware``
(bare unit-test apps) are exempt — without a session there is nothing to
bind a token to.

This lifts the design the pagebuilder module shipped first
(``pagebuilder/security.py``) into the framework, so every module shares
one header name and one token-discovery convention. Sign-in clears the users
session, rotating its token; principal changes that retain the session must
call ``rotate_csrf_token`` before rendering the next page.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

__all__ = [
    "CSRF_HEADER",
    "RequiresCsrf",
    "get_csrf_token",
    "require_browser_origin",
    "rotate_csrf_token",
]

CSRF_HEADER = "X-CSRF-Token"
_SESSION_KEY = "sm_csrf_token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def require_browser_origin(request: Request) -> None:
    """Refuse browser mutations the browser itself labels ``cross-site``.

    Origin/Referer are deliberately not compared with ``request.base_url``: behind
    a TLS-terminating proxy without trusted-proxy handling the app sees
    ``http://internal`` while the browser sends ``https://app.example``, which
    would refuse every sign-in and sign-out. Login CSRF is stopped by the session
    CSRF token (``require_browser_csrf``); this check adds the fetch-metadata
    refusal for browsers that send it.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="Browser request source refused")


def get_csrf_token(request: Request) -> str:
    """Return the session's CSRF token, generating and persisting it if needed.

    Returns ``""`` when no session is mounted so view code can pass it
    straight into page props without a None check.

    Concurrent cold requests on the same not-yet-issued session (e.g. two
    tabs opened in the same instant) can each read no token, mint their own,
    and race to write it back — whichever ``Set-Cookie`` lands last wins, so
    the loser's freshly-rendered token can end up mismatched with the
    session that's actually stored. This is inherent to signed-cookie
    sessions: each request deserializes and mutates its own private copy,
    there's no shared server-side store to lock. It self-heals on the very
    next render (that request reads the now-settled token), so it's not
    worth adding a server-side token store just to close this window.
    """
    session = request.scope.get("session")
    if session is None:
        return ""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> None:
    """Discard the old token; the next page render mints a fresh one.

    Use when changing the principal while deliberately retaining the session.
    Clearing the whole session already discards the token. No session is a no-op.
    """
    session = request.scope.get("session")
    if session is not None:
        session.pop(_SESSION_KEY, None)


class RequiresCsrf:
    """FastAPI dependency enforcing the CSRF header on unsafe methods.

    Attach at the router level so every mutation under it is covered::

        router = APIRouter(dependencies=[Depends(RequiresCsrf())])
    """

    async def __call__(self, request: Request) -> None:
        # async so FastAPI awaits it inline — a sync dependency would take a
        # threadpool hop on every mutation request for a microsecond check.
        if request.method not in _UNSAFE_METHODS:
            return
        session = request.scope.get("session")
        if session is None:
            return  # no session mounted — nothing to bind a token to
        # Read (never mint) the token here: a rejected request must not mutate
        # the session or re-issue the cookie. Compare as bytes — str
        # compare_digest raises TypeError on non-ASCII input, and header
        # values are attacker-controlled latin-1, which would turn a bad
        # token into a 500 instead of a 403.
        expected = session.get(_SESSION_KEY, "")
        provided = request.headers.get(CSRF_HEADER, "")
        if (
            not provided
            or not expected
            or not secrets.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"CSRF token missing or invalid — read it via get_csrf_token "
                    f"(exposed in the view's props) and send it as {CSRF_HEADER}."
                ),
            )
