"""Safety net for user-influenced redirect targets.

Several flows park "where the visitor was heading" somewhere a browser can
reach — ``AuthMiddleware`` stashes it in the session before bouncing an
anonymous visitor to login, ``site_lock`` puts it in the unlock page's query
string. Anything replayed into a ``Location`` header is an open-redirect
surface, so every producer and consumer funnels through :func:`safe_next`.

This lives in the framework rather than in whichever module needed it first:
it encodes no plugin knowledge, and duplicating URL-safety rules per module is
how one copy ends up missing a case.
"""

from __future__ import annotations

DEFAULT_FALLBACK = "/"

SESSION_NEXT_KEY = "next"
"""Session key holding the post-login destination.

This is the contract between ``AuthMiddleware`` (which writes it when it
bounces an anonymous visitor) and whichever provider completes the login and
sends the visitor onward. It is shared rather than redeclared per module
because a provider that reads a *different* key silently loses every deep
link — which is exactly how the local provider drifted from the Keycloak one.
"""


def safe_next(raw: str | None, *, fallback: str = DEFAULT_FALLBACK) -> str:
    """Return ``raw`` if it is a same-site absolute path, else ``fallback``.

    Rejects protocol-relative (``//host``) and backslash-prefixed (``/\\host``)
    targets — browsers resolve both off-site — plus anything carrying CR/LF,
    which could otherwise be smuggled into the redirect header.
    """
    if not raw or not raw.startswith("/"):
        return fallback
    if raw.startswith(("//", "/\\")):
        return fallback
    if "\r" in raw or "\n" in raw:
        return fallback
    return raw


def safe_next_or_none(raw: str | None) -> str | None:
    """Like :func:`safe_next`, but ``None`` when ``raw`` is unusable.

    Callers that fall back to a *configured* destination (rather than ``/``)
    need to tell "no target" apart from "the target was ``/``" — returning the
    fallback would silently outrank a configured ``login_redirect_url``.
    """
    result = safe_next(raw, fallback="")
    return result or None


__all__ = ["DEFAULT_FALLBACK", "SESSION_NEXT_KEY", "safe_next", "safe_next_or_none"]
