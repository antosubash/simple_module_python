"""Phase 5 of boot — every module's declarative registration hooks.

Extracted from ``app_builder.py`` to keep that file readable; this is the one
place that knows the full set of hooks a module may implement, and the order
they run in. ``app_builder.create_app`` is the only intended caller.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from simple_module_core.body_limits import BodyLimitRegistry
from simple_module_core.cors import CorsPolicyRegistry
from simple_module_core.deprecation import deprecate
from simple_module_core.rate_limit import RateLimitRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI


@dataclass(slots=True)
class RequestRegistries:
    """The request-pipeline registries modules fill via ``_request_hooks``.

    ``attach`` publishes them on ``app.state`` -- ``body_limits``,
    ``cors_policies`` and ``rate_limit_rules`` -- where the middleware reads them.
    """

    body_limits: BodyLimitRegistry = field(default_factory=BodyLimitRegistry)
    cors: CorsPolicyRegistry = field(default_factory=CorsPolicyRegistry)
    rate_limits: RateLimitRegistry = field(default_factory=RateLimitRegistry)

    def attach(self, app: FastAPI) -> None:
        app.state.body_limits = self.body_limits
        app.state.cors_policies = self.cors
        app.state.rate_limit_rules = self.rate_limits


def run_module_registrations(
    modules: list,
    *,
    app: FastAPI,
    event_bus,
    invalidation_bus,
    menu_registry,
    perm_registry,
    ff_registry,
    health_registry,
    public_route_registry,
    setup_registry,
    design_pack_registry,
    audit_link_registry,
    csp_registry,
    request_registries: RequestRegistries,
    resource_type_registry=None,
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
        mod.register_invalidations(invalidation_bus, app)
        health_registry.set_owner(mod.meta.name)
        mod.register_health_checks(health_registry)
        mod.register_public_routes(public_route_registry)
        mod.register_body_limits(request_registries.body_limits)
        mod.register_cors_policies(request_registries.cors)
        mod.register_rate_limits(request_registries.rate_limits)
        setup_registry.set_owner(mod.meta.name)
        mod.register_setup_steps(setup_registry)
        # csp before design packs — the documented lifecycle order
        # (docs/framework/lifecycle.md).
        mod.register_csp_sources(csp_registry)
        mod.register_design_packs(design_pack_registry)
        mod.register_audit_links(audit_link_registry)
        if resource_type_registry is not None:
            mod.register_resource_types(resource_type_registry)

    health_registry.set_owner("")
    setup_registry.set_owner("")


_ONE_ARG_EVENT_HANDLERS = deprecate(
    "register_event_handlers(self, bus) without the app parameter",
    remove_in="0.1.0",
    use="register_event_handlers(self, bus, app=None)",
)


def dispatch_event_handlers(mod, event_bus, app: FastAPI) -> None:
    """Call ``mod.register_event_handlers`` with or without ``app``.

    Deprecated back-compat for modules that still override the one-arg form
    ``(self, bus)``; passing ``app=`` to those crashes. Removed in 0.1.0.
    """
    sig = inspect.signature(mod.register_event_handlers)
    accepts_app = "app" in sig.parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_app:
        mod.register_event_handlers(event_bus, app=app)
    else:
        _ONE_ARG_EVENT_HANDLERS.warn()
        mod.register_event_handlers(event_bus)
