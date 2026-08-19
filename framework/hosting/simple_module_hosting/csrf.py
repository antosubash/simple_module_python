"""Opt-in session-bound CSRF protection for module mutation endpoints.

The framework's baseline CSRF defence is ``SameSite=Lax`` on the session
cookie: browsers don't attach it to cross-site POSTs, so a forged form
submit arrives unauthenticated. Modules that want defence in depth (or must
satisfy a stricter audit) opt into a token check per router::

    from simple_module_hosting.csrf import RequiresCsrf, get_csrf_token

    router = APIRouter(dependencies=[Depends(RequiresCsrf())])

    # expose the token to the frontend, e.g. as an Inertia prop:
    await inertia.render("MyModule/Page", {"csrf_token": get_csrf_token(request)})

Callers send the token back as ``X-CSRF-Token`` on POST/PUT/PATCH/DELETE.
Safe methods are never checked. Apps that mount no ``SessionMiddleware``
(bare unit-test apps) are exempt — without a session there is nothing to
bind a token to.

This lifts the design the pagebuilder module shipped first
(``pagebuilder/security.py``) into the framework, so every module shares
one header name and one token-discovery convention.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

__all__ = ["CSRF_HEADER", "RequiresCsrf", "get_csrf_token"]

CSRF_HEADER = "X-CSRF-Token"
_SESSION_KEY = "sm_csrf_token"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_csrf_token(request: Request) -> str:
    """Return the session's CSRF token, generating and persisting it if needed.

    Returns ``""`` when no session is mounted so view code can pass it
    straight into page props without a None check.
    """
    session = request.scope.get("session")
    if session is None:
        return ""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


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
