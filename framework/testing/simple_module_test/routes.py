"""Enumerate an app's effective route paths, robust to lazy router inclusion.

FastAPI 0.137 / Starlette 1.3 made ``include_router()`` lazy: an included router
now appears in ``app.routes`` as a ``_IncludedRouter`` wrapper that carries no
``.path`` and resolves its routes only at request time. Code that introspects
``app.routes`` by ``.path`` therefore no longer sees routes contributed via
``include_router`` — including every module's API/view routes and the health
router. (Routes still resolve correctly at request time; only static
introspection broke.)

:func:`effective_route_paths` reads the OpenAPI schema instead — a stable public
API that lists every schema-included route with its fully-resolved prefix — and
unions it with any top-level routes/mounts that still carry a ``.path`` directly
(e.g. ``StaticFiles`` mounts). This works across FastAPI versions and is the
supported way to assert on registered routes.
"""

from __future__ import annotations

from fastapi import FastAPI


def effective_route_paths(app: FastAPI) -> set[str]:
    """Return the set of route paths registered on ``app``.

    Includes schema routes contributed via ``include_router`` (resolved through
    the OpenAPI schema, so FastAPI's lazy ``_IncludedRouter`` wrappers don't hide
    them) plus any top-level mounts. Routes registered with
    ``include_in_schema=False`` — e.g. the bare-prefix Inertia aliases — are not
    listed here; assert those with a request instead.
    """
    paths = set(app.openapi().get("paths", {}).keys())
    paths |= {r.path for r in app.routes if getattr(r, "path", None) is not None}
    return paths
