"""Inertia shared props contributed by the users module.

The public shell (landing page, ``PublicLayout``) has to know whether local
signup is open *before* it renders a "Sign up" link: ``/users/register`` raises
404 when ``allow_signup`` is off, so a link rendered unconditionally walks every
visitor into a dead end.

Exposed as its own top-level key rather than folded into ``auth`` — the
framework owns that block and a provider may not overwrite it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request


def users_shared_props(request: Request) -> dict:
    """Whether local self-signup is currently accepted.

    Runs on every request, so it only reads already-hydrated state. Defaults to
    closed: if settings are missing, the safe answer is "no signup link" rather
    than a link that 404s.
    """
    state = getattr(request.app.state, "users", None)
    settings = getattr(state, "settings", None)
    return {"signup": {"allowed": bool(getattr(settings, "allow_signup", False))}}
