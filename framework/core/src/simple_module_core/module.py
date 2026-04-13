"""Module base class and metadata."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry


@dataclass(frozen=True)
class ModuleMeta:
    """Metadata describing a module."""

    name: str
    route_prefix: str = ""
    view_prefix: str = ""
    depends_on: list[str] = field(default_factory=list)
    version: str = "1.0.0"


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

    def register_event_handlers(self, bus: EventBus) -> None:
        """Subscribe to events published by other modules."""

    def register_health_checks(self, registry: HealthRegistry) -> None:
        """Contribute health checks for the ``/health/ready`` endpoint."""

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

    # ── Lifecycle ─────────────────────────────────────────────

    async def on_startup(self, app: FastAPI) -> None:
        """Called after all modules are registered, during app startup."""

    async def on_shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""
