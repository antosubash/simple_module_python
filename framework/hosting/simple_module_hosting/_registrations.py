"""Phase 5 of boot — every module's declarative registration hooks.

Extracted from ``app_builder.py`` to keep that file readable; this is the one
place that knows the full set of hooks a module may implement, and the order
they run in. ``app_builder.create_app`` is the only intended caller.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def run_module_registrations(
    modules: list,
    *,
    app: FastAPI,
    event_bus,
    menu_registry,
    perm_registry,
    ff_registry,
    health_registry,
    public_route_registry,
    design_pack_registry,
    audit_link_registry,
    csp_registry,
) -> None:
    """Invoke each module's registration hooks, in dependency order.

    Health checks are attributed to the module that registers them, so the
    dashboard can report health per module rather than one global number. The
    owner is cleared afterwards: anything registered later — a module's
    ``on_startup``, say — belongs to no module in this loop, and inheriting
    the last one's name would be a lie.
    """
    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        dispatch_event_handlers(mod, event_bus, app)
        health_registry.set_owner(mod.meta.name)
        mod.register_health_checks(health_registry)
        mod.register_public_routes(public_route_registry)
        # csp before design packs — the documented lifecycle order
        # (docs/framework/lifecycle.md).
        mod.register_csp_sources(csp_registry)
        mod.register_design_packs(design_pack_registry)
        mod.register_audit_links(audit_link_registry)

    health_registry.set_owner("")


def dispatch_event_handlers(mod, event_bus, app: FastAPI) -> None:
    """Call ``mod.register_event_handlers`` with or without ``app``.

    Back-compat shim for modules that still override the one-arg form
    ``(self, bus)``; passing ``app=`` to those crashes.
    """
    sig = inspect.signature(mod.register_event_handlers)
    accepts_app = "app" in sig.parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_app:
        mod.register_event_handlers(event_bus, app=app)
    else:
        mod.register_event_handlers(event_bus)
