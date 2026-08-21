"""Permanent redirects from the pre-``/admin`` view URLs.

The admin screens used to be scattered across the URL space — ``/settings/``,
``/audit_log/``, ``/users/admin`` — with nothing marking them as a section.
They now live under ``/admin/``. Existing bookmarks, browser history and any
link written down elsewhere would otherwise 404.

Only *view* URLs moved. ``/api/*`` is a separate contract with external
callers and is deliberately untouched.

These live at the host rather than in the modules because a module can only
serve routes under its own ``view_prefix`` — having moved, it no longer owns
the path it moved away from.

Scheduled for removal one minor release after the move; a 301 is cacheable,
so browsers that have seen it will keep following it long after the route
itself is gone.
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter(include_in_schema=False)

# old prefix -> new prefix. Longest match wins, so order is irrelevant.
_MOVED: dict[str, str] = {
    "/users/admin": "/admin/users",
    "/settings": "/admin/settings",
    "/audit_log": "/admin/audit-log",
    "/feature_flags": "/admin/feature-flags",
    "/branding": "/admin/branding",
    "/permissions": "/admin/permissions",
    "/dashboard/doctor": "/admin/doctor",
}


def _register(old_prefix: str, new_prefix: str) -> None:
    async def redirect(path: str = "") -> RedirectResponse:
        suffix = f"/{path}" if path else "/"
        return RedirectResponse(f"{new_prefix}{suffix}", status_code=301)

    async def redirect_bare() -> RedirectResponse:
        return RedirectResponse(f"{new_prefix}/", status_code=301)

    # Bare form and trailing-slash form both land on the new section root.
    router.add_api_route(old_prefix, redirect_bare, methods=["GET"], name=f"legacy{old_prefix}")
    router.add_api_route(
        f"{old_prefix}/{{path:path}}",
        redirect,
        methods=["GET"],
        name=f"legacy{old_prefix}_sub",
    )


for _old, _new in _MOVED.items():
    _register(_old, _new)
