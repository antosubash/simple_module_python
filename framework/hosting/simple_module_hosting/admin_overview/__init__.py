"""The ``/admin`` overview, shipped with the framework.

The sidebar's "Administration" link and the AdminLayout badge point every app
at ``/admin``. The page used to live in this repository's own host, so an app
made by ``smpy new`` answered 404 there (GH #914). ``create_app`` now mounts
it for every host, the way it mounts the setup wizard (GH #351).

No module owns the admin section as a whole — it is assembled from whatever
modules happen to be installed — so the framework serves it rather than one
plugin claiming ``/admin`` as its ``view_prefix``.

The page is registered in ``modules.generated.ts`` under :data:`PAGES_NAME`,
like a module's ``pages/``, so a host's Vite build picks it up from the wheel.
"""

from __future__ import annotations

from pathlib import Path

#: The ``modules.generated.ts`` key the overview's pages are registered under.
PAGES_NAME = "Admin"

#: ``pages/Overview.tsx`` as an Inertia page key.
PAGE_OVERVIEW = f"{PAGES_NAME}/Overview"

_PACKAGE_DIR = Path(__file__).resolve().parent


def package_dir() -> Path:
    """The overview's frontend root."""
    return _PACKAGE_DIR


def pages_dir() -> Path:
    return _PACKAGE_DIR / "pages"


def mount_admin_overview(app) -> None:
    """Mount ``/admin``; every other ``/admin/*`` path belongs to a module."""
    from simple_module_hosting.admin_overview.routes import router

    app.include_router(router)
