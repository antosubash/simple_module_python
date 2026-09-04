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


def non_empty_redirect(value: str, *, default: str) -> str:
    """Normalise a configured redirect destination, never returning ``""``.

    Any auth provider can expose a ``login_redirect_url``-style setting, and
    nothing stops an admin clearing it in the generic module-settings editor.
    Every consumer treats the value as a destination — Inertia's
    ``router.visit("")`` silently reloads the current page, and an empty
    ``Location`` header is a broken redirect — so providers normalise on their
    settings class, where hydration and ``apply_changes_and_reload`` both run.
    It lives here rather than in one provider because the providers must not
    import each other (cross-module coupling), and this is the same concern as
    the rest of this module.
    """
    return value.strip() or default


__all__ = [
    "DEFAULT_FALLBACK",
    "SESSION_NEXT_KEY",
    "non_empty_redirect",
    "safe_next",
    "safe_next_or_none",
]
