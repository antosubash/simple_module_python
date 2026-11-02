"""Mount a module's routers onto the app using its ``ModuleMeta`` prefixes.

Split out of ``_phase_helpers`` once the admin router made this its own
responsibility — and to keep both files under the 300-line cap.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute

from simple_module_hosting._openapi import make_unique_id_function
from simple_module_hosting.token_guard import page_route

__all__ = ["wire_module_routes"]


def wire_module_routes(app: FastAPI, module) -> bool:
    """Attach a module's API + view (+ admin view) routers to ``app``.

    Returns whether the module mounted any view routes. ``view_prefix=""`` means
    both "no views" and "mounted at /", so only a router that actually received
    routes says which one it is (#435).

    The single canonical implementation so ``create_app`` and the test harness
    in ``simple_module_test`` stay in lockstep if ``ModuleBase`` ever gains
    a new router type.

    Each prefix is given to ``include_router``, not to the ``APIRouter``: the
    effective paths are the same, but FastAPI only checks an un-prefixed
    include for empty paths, and that check resolves every nested route
    (dependants, signatures, adapters; ~0.2 s per app build) that would
    otherwise resolve lazily on first use.
    """
    api_router = APIRouter(
        tags=[module.meta.name],
        generate_unique_id_function=make_unique_id_function(),
    )
    # Views are Inertia pages, not part of the published JSON API (#456), and
    # carry the page marker: an API token is refused on every page, gated or
    # not (``token_guard``).
    pages = [Depends(page_route)]
    view_router = APIRouter(
        tags=[f"{module.meta.name} Views"],
        include_in_schema=False,
        dependencies=pages,
    )
    module.register_routes(api_router, view_router)
    _clone_bare_prefix_route(view_router, module.meta.view_prefix)
    has_views = bool(view_router.routes)
    app.include_router(api_router, prefix=module.meta.route_prefix)
    app.include_router(view_router, prefix=module.meta.view_prefix, include_in_schema=False)

    # Second view router for modules that serve both public and admin pages
    # and therefore cannot express both under a single view_prefix — see
    # ``ModuleMeta.admin_view_prefix``.
    admin_prefix = getattr(module.meta, "admin_view_prefix", "")
    if admin_prefix:
        admin_router = APIRouter(
            tags=[f"{module.meta.name} Admin Views"],
            include_in_schema=False,
            dependencies=pages,
        )
        module.register_admin_routes(admin_router)
        _clone_bare_prefix_route(admin_router, admin_prefix)
        app.include_router(admin_router, prefix=admin_prefix, include_in_schema=False)
    return has_views


def _clone_bare_prefix_route(router: APIRouter, prefix: str) -> None:
    """Serve ``"/foo"`` as well as ``"/foo/"`` for a bare-prefix route.

    Without this, FastAPI's ``redirect_slashes=True`` fires a 307 to
    ``"/foo/"``, which clients like httpx strip ``X-Inertia`` from on follow —
    turning that Inertia navigation into a broken HTML response.

    Only covers routes declared *directly* on the router. A route contributed
    via ``router.include_router(...)`` — which is how most modules register —
    is not visible here: ``include_router`` stores a placeholder and only
    flattens into ``APIRoute`` objects later, so there is nothing to match
    yet. Modules in that (majority) case point their menu item at the
    canonical trailing-slash URL instead, which costs no redirect either.
    """
    if not prefix:
        return
    # Paths are relative to the router: the prefix is added on include.
    for route in list(router.routes):
        if isinstance(route, APIRoute) and route.path == "/":
            router.add_api_route(
                "",
                route.endpoint,
                methods=list(route.methods or {"GET"}),
                response_model=route.response_model,
                include_in_schema=False,
                dependencies=route.dependencies,
                name=f"{route.name}__bare",
            )
