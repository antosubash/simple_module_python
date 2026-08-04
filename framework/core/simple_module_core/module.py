"""Module base class and metadata."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from simple_module_core.design_packs import DesignPackRegistry
    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_core.public_routes import PublicRouteRegistry


@dataclass(frozen=True)
class ModuleMeta:
    """Metadata describing a module."""

    name: str
    route_prefix: str = ""
    view_prefix: str = ""
    depends_on: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    requires_framework: str | None = None
    """PEP 440 specifier for the framework API version this module supports.

    Example: ``">=1.0,<2.0"``. When set, the module is rejected at boot if the
    installed ``simple_module_core.FRAMEWORK_API_VERSION`` does not satisfy it.
    When ``None``, no compatibility check is performed (legacy modules).
    """


class ModuleBase(ABC):
    """Base class for all modules.

    Subclasses override only the methods they need.
    Every method has a default no-op implementation.

    Hook execution order during app boot:

        Phase 1: Bootstrap
          - Load framework Settings
          - Discover & topological-sort modules
          - Run diagnostics (dev only)

        Phase 2: App creation
          - Create FastAPI app
          - Store framework registries + settings on app.state

        Phase 3: Module settings
          - register_settings(app)

        Phase 4: Module registrations
          - register_menu_items(registry)
          - register_permissions(registry)
          - register_feature_flags(registry)
          - register_event_handlers(bus)
          - register_health_checks(registry)

        Phase 5: Database
          - init_db() -> DatabaseState
          - register_listeners(db_state)

        Phase 6: App wiring
          - Inertia setup
          - register_exception_handlers(app)
          - Middleware pipeline (register_middleware per module)
          - register_routes(api_router, view_router)
          - Mount health router + static files

        Phase 7: Runtime (async)
          - on_startup(app) — per module, in dependency order
          - on_shutdown(app) — per module, reverse order
    """

    meta: ModuleMeta

    # ── Settings ─────────────────────────────────────────────

    def register_settings(self, app: FastAPI) -> None:
        """Load module-specific settings and store on ``app.state``.

        Called before all other registration hooks. Convention:
        store as ``app.state.<module_name_lower>_settings``.
        """

    # ── Service Registration ──────────────────────────────────

    def register_routes(
        self,
        api_router: APIRouter,
        view_router: APIRouter,
    ) -> None:
        """Register API endpoints and Inertia view routes."""

    def register_menu_items(self, registry: MenuRegistry) -> None:
        """Contribute menu items visible in the UI."""

    def register_permissions(self, registry: PermissionRegistry) -> None:
        """Declare permissions this module uses."""

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        """Declare feature flags this module exposes."""

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        """Subscribe to events published by other modules.

        ``app`` is optional for back-compat; pass it through to handlers
        that need ``app.state.sm.db.session_factory`` to persist on the
        framework's engine instead of building their own.
        """

    def register_health_checks(self, registry: HealthRegistry) -> None:
        """Contribute health checks for the ``/health/ready`` endpoint."""

    def register_public_routes(self, registry: PublicRouteRegistry) -> None:
        """Declare routes that must bypass authentication (anonymous access).

        ``AuthMiddleware`` gates every request behind the active auth provider.
        Override this hook to exempt read-only or webhook routes that are meant
        to be reached without a session — e.g. a STAC / OGC API surface::

            def register_public_routes(self, registry):
                registry.add_prefix("/api/gis/stac")
                registry.add_regex(
                    r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"}
                )

        Rules are method-aware, so a GET read route nested under a prefix that
        also carries POST/PATCH mutations can be exempted without opening the
        mutations. Called once at boot, in dependency order.
        """

    def register_design_packs(self, registry: DesignPackRegistry) -> None:
        """Declare design packs this module ships for the public site.

        A design pack is a stylesheet that restyles the reader-facing site by
        overriding the base tokens beneath a ``<value>-root`` class. Override
        this hook to make the pack selectable in branding::

            def register_design_packs(self, registry):
                registry.register(DesignPack(value="gca", label="Canopy Atlas"))

        Registering only advertises the pack — the stylesheet itself still
        reaches the bundle through the host's ``styles.css``. Slugs are unique
        across modules; a collision raises at boot. Called once, in dependency
        order.
        """

    def register_middleware(self, app: FastAPI) -> None:
        """Add middleware to the application.

        Called after core middleware (session, security headers) positioning
        is established but before the app starts.  Modules that need to
        inject middleware (e.g. auth) override this method.
        """

    def register_exception_handlers(self, app: FastAPI) -> None:
        """Register custom exception handlers on the application.

        Called after framework exception handlers are set up.
        """

    # ── Asset contribution (templates & static files) ─────────

    def template_dirs(self) -> list[Path]:
        """Return Jinja2 template directories this module contributes.

        The host aggregates all modules' template dirs (plus its own) into the
        Jinja2 loader, so templates in ``<module>/templates/`` become resolvable
        from any module. Return an empty list (default) to contribute none.

        Each path is typically computed via
        ``importlib.resources.files(__package__) / "templates"`` so it resolves
        correctly when the module is installed as a PyPI package.
        """
        return []

    def static_mounts(self) -> dict[str, Path]:
        """Return static file mounts this module contributes.

        Mapping of URL prefix → filesystem directory. The host mounts each entry
        via ``StaticFiles`` during app boot. Convention: prefix with
        ``/modules/<name>/static`` to avoid collisions with the host's own
        ``/static`` mount. Return an empty dict (default) to contribute none.
        """
        return {}

    def locale_dirs(self) -> dict[str, Path]:
        """Return ``{namespace: directory}`` mapping for locale JSON files.

        Default returns an empty dict. Override to contribute a module's
        locales::

            return {
                "products": importlib.resources.files(__package__) / "locales"
            }

        The namespace becomes the key prefix in the merged i18n registry.
        A file ``locales/en.json`` containing ``{"browse": {"title": "X"}}``
        becomes the key ``products.browse.title`` at runtime.

        Convention: use the module's lowercase name as the namespace.
        """
        return {}

    # ── Lifecycle ─────────────────────────────────────────────

    async def on_startup(self, app: FastAPI) -> None:
        """Called after all modules are registered, during app startup."""

    async def on_shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""
