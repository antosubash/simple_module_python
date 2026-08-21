"""Mount a module's routers onto the app using its ``ModuleMeta`` prefixes.

Split out of ``_phase_helpers`` once the admin router made this its own
responsibility — and to keep both files under the 300-line cap.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

__all__ = ["wire_module_routes"]


def wire_module_routes(app: FastAPI, module) -> None:
    """Attach a module's API + view (+ admin view) routers to ``app``.

    The single canonical implementation so ``create_app`` and the test harness
    in ``simple_module_test`` stay in lockstep if ``ModuleBase`` ever gains
    a new router type.
    """
    api_router = APIRouter(prefix=module.meta.route_prefix, tags=[module.meta.name])
    view_router = APIRouter(prefix=module.meta.view_prefix, tags=[f"{module.meta.name} Views"])
    module.register_routes(api_router, view_router)
    _clone_bare_prefix_route(view_router, module.meta.view_prefix)
    app.include_router(api_router)
    app.include_router(view_router)

    # Second view router for modules that serve both public and admin pages
    # and therefore cannot express both under a single view_prefix — see
    # ``ModuleMeta.admin_view_prefix``.
    admin_prefix = getattr(module.meta, "admin_view_prefix", "")
    if admin_prefix:
        admin_router = APIRouter(
            prefix=admin_prefix,
            tags=[f"{module.meta.name} Admin Views"],
        )
        module.register_admin_routes(admin_router)
        _clone_bare_prefix_route(admin_router, admin_prefix)
        app.include_router(admin_router)


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
    bare_target = f"{prefix}/"
    for route in list(router.routes):
        if isinstance(route, APIRoute) and route.path == bare_target:
            router.add_api_route(
                "",
                route.endpoint,
                methods=list(route.methods or {"GET"}),
                response_model=route.response_model,
                include_in_schema=False,
                dependencies=route.dependencies,
                name=f"{route.name}__bare",
            )
