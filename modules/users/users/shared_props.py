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

from users.demo_guard import is_demo_session

if TYPE_CHECKING:
    from starlette.requests import Request


def users_shared_props(request: Request) -> dict:
    """Whether local self-signup is accepted, and whether this is a demo session.

    Runs on every request, so it only reads already-hydrated state. Defaults to
    closed: if settings are missing, the safe answer is "no signup link" rather
    than a link that 404s.

    The ``demo`` block is what lets every shell show a standing banner. It is
    per-*session*, not per-install: an operator signed in to their own account
    on a demo instance is doing real work and should not be told otherwise,
    and it is the demo visitor who needs to know their saves will bounce.
    """
    state = getattr(request.app.state, "users", None)
    settings = getattr(state, "settings", None)
    demo_active = bool(getattr(settings, "demo_mode", False)) and is_demo_session(
        getattr(request, "scope", {}), getattr(state, "demo_user_id", None)
    )
    return {
        "signup": {"allowed": bool(getattr(settings, "allow_signup", False))},
        "demo": {
            "active": demo_active,
            "readOnly": demo_active and bool(getattr(settings, "demo_read_only", True)),
        },
    }
