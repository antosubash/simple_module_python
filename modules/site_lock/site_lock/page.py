"""Render the standalone unlock page.

Kept out of ``middleware.py`` so the escaping and ``next``-sanitisation rules
can be unit-tested without an ASGI harness, and so both files stay well under
the 300-line cap.
"""

from __future__ import annotations

import html
import importlib.resources
from string import Template

_TEMPLATE = Template(
    (importlib.resources.files(__package__) / "templates" / "unlock.html").read_text(
        encoding="utf-8"
    )
)

_DEFAULT_MESSAGE = "This site is not public yet. Enter the password to continue."
_ERROR_BLOCK = '<p class="error" role="alert">{message}</p>'


def safe_next(raw: str | None) -> str:
    """Return ``raw`` if it is a same-site absolute path, else ``/``.

    Rejects protocol-relative (``//host``) and backslash-prefixed (``/\\host``)
    targets — browsers resolve both off-site — plus anything carrying CR/LF,
    which could otherwise be smuggled into the redirect header. Without this
    the gate would be an open redirect.
    """
    if not raw or not raw.startswith("/"):
        return "/"
    if raw.startswith(("//", "/\\")):
        return "/"
    if "\r" in raw or "\n" in raw:
        return "/"
    return raw


def render_unlock_page(
    *,
    message: str = "",
    error: str = "",
    next_url: str = "/",
) -> str:
    """Render the gate page. Every interpolated value is HTML-escaped."""
    return _TEMPLATE.safe_substitute(
        message=html.escape(message or _DEFAULT_MESSAGE),
        error=_ERROR_BLOCK.format(message=html.escape(error)) if error else "",
        next_url=html.escape(safe_next(next_url), quote=True),
    )


__all__ = ["render_unlock_page", "safe_next"]
