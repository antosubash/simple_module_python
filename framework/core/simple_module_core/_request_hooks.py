"""Request-pipeline registration hooks, split out of ``ModuleBase``.

Everything a module declares about how HTTP requests reach it -- anonymous
routes, body ceilings, CSP origins, CORS policies, rate limits, middleware and
exception handlers. ``ModuleBase`` inherits this mixin, so ``from
simple_module_core.module import ModuleBase`` and every override are unchanged.
All hooks are no-ops by default and run once at boot, in dependency order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from simple_module_core.body_limits import BodyLimitRegistry
    from simple_module_core.cors import CorsPolicyRegistry
    from simple_module_core.csp import CspSourceRegistry
    from simple_module_core.public_routes import PublicRouteRegistry
    from simple_module_core.rate_limit import RateLimitRegistry


class RequestHooksMixin:
    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        """Declare routes that must bypass authentication (anonymous access).

        ``AuthMiddleware`` gates every request behind the active auth provider.
        Override this hook to exempt read-only or webhook routes that are meant
        to be reached without a session — e.g. a STAC / OGC API surface::

            def register_public_routes(self, registry):
                registry.add_prefix("/api/gis/stac")
                registry.add_regex(r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"})

        Rules are method-aware, so a GET read route nested under a prefix that
        also carries POST/PATCH mutations can be exempted without opening the
        mutations. Called once at boot, in dependency order.
        """

    def register_body_limits(self, registry: BodyLimitRegistry) -> None:
        """Per-route request-body ceilings; see docs/framework/request-guards.md."""

    def register_csp_sources(self, registry: CspSourceRegistry) -> None:
        """Declare external origins this module's frontend loads assets from.

        The host ships a strict Content-Security-Policy; a module whose
        pages pull a stylesheet, font, or API from another origin must
        declare it here or the browser blocks the request::

            def register_csp_sources(self, registry):
                registry.add("style-src", "https://rsms.me")
                registry.add("font-src", "https://rsms.me")

        Fetch directives only; invalid declarations raise at boot. Runs once,
        *before* DB settings hydrate — for an origin read from settings use
        ``registry.add_provider(lambda app: [(directive, source)])`` (sync,
        in-memory state only, evaluated per response).
        """

    def register_middleware(self, app: FastAPI) -> None:
        """Add middleware to the application.

        Called after core middleware (session, security headers) positioning
        is established but before the app starts.
        """

    def register_exception_handlers(self, app: FastAPI) -> None:
        """Register custom exception handlers (after the framework's own)."""

    def register_cors_policies(self, registry: CorsPolicyRegistry) -> None:
        """Declare cross-origin policies for this module's routes.

        The host already allows its configured origins on ``/api/``; override
        this for a surface with different rules, e.g. publicly served files::

            def register_cors_policies(self, registry):
                registry.add_prefix(
                    "/files/public/",
                    CorsPolicy(origins=("*",), allow_credentials=False, methods=("GET", "HEAD")),
                    enabled=lambda: self._public_cors_on(),
                )

        The most specific path match wins (exact, regex, longest prefix);
        ``enabled`` is evaluated per request. A wildcard origin cannot be
        combined with credentials. Called once at boot, in dependency order.
        """

    def register_rate_limits(self, registry: RateLimitRegistry) -> None:
        """Declare per-route rate limits for this module's endpoints.

        ::

            def register_rate_limits(self, registry):
                registry.add_exact(
                    "/api/orders/export", RateLimitRule("5/minute", key="user")
                )

        ``key`` picks who shares a budget: the signed-in user, the client IP,
        ``user_or_ip`` (user when signed in, else IP) or the active tenant.
        The most specific path match wins. Called once at boot, in dependency
        order.
        """
