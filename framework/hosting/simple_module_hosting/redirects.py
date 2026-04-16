"""Shared helpers for validating redirect targets.

A raw ``Referer`` header is attacker-controlled — a crafted form on a third
party site can set it to any value. Any endpoint that 303s back to the
referring page must validate the URL is same-origin before trusting it, or
become a reflected open-redirect.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request


def safe_referer_or_root(request: Request) -> str:
    """Return the Referer iff it's same-origin; otherwise fall back to ``/``.

    Only honors references that (a) resolve to the same scheme+host as the
    current request, or (b) are relative paths that don't try to escape to a
    protocol-relative URL (``//evil.example``).
    """
    referer = request.headers.get("referer")
    if not referer:
        return "/"

    # Protocol-relative URLs like "//evil.example/foo" resolve against the
    # origin in browsers but leave the site — reject them.
    if referer.startswith("//"):
        return "/"

    parsed = urlsplit(referer)
    # Relative path with no scheme+host → same-origin by construction.
    if not parsed.scheme and not parsed.netloc:
        return referer if referer.startswith("/") else "/"

    # Absolute URL → must match the current request's origin.
    current = request.url
    if parsed.scheme == current.scheme and parsed.netloc == current.netloc:
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    return "/"
