"""Shared helpers for validating redirect targets.

A raw ``Referer`` header is attacker-controlled — a crafted form on a third
party site can set it to any value. Any endpoint that 303s back to the
referring page must validate the URL is same-origin before trusting it, or
become a reflected open-redirect.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request
from simple_module_core.redirect_safety import safe_next


def safe_referer_or_root(request: Request) -> str:
    """Return the Referer iff it's same-origin; otherwise fall back to ``/``.

    Only honors references that (a) resolve to the same scheme+host as the
    current request, or (b) are relative paths. Either way the result is run
    through :func:`~simple_module_core.redirect_safety.safe_next`, which is the
    single owner of what counts as a safe same-site target.
    """
    referer = request.headers.get("referer")
    if not referer:
        return "/"

    parsed = urlsplit(referer)
    # Relative reference (no scheme+host). ``safe_next`` owns the rules here —
    # it rejects protocol-relative ("//host") and backslash-prefixed ("/\\host")
    # targets, both of which browsers resolve off-site, plus anything carrying
    # CR/LF that could be smuggled into the Location header. Delegated rather
    # than restated so the two sanitisers cannot drift: a second copy that
    # missed one of those cases is exactly how this becomes an open redirect.
    if not parsed.scheme and not parsed.netloc:
        return safe_next(referer)

    # Absolute URL → must match the current request's origin.
    current = request.url
    if parsed.scheme == current.scheme and parsed.netloc == current.netloc:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return safe_next(path)

    return "/"
