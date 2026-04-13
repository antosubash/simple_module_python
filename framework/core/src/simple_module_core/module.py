"""Module base class and metadata."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
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
    """

    meta: ModuleMeta

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

    def register_middleware(self, app: FastAPI) -> None:
        """Add middleware to the application.

        Called after core middleware (session, security headers) positioning
        is established but before the app starts.  Modules that need to
        inject middleware (e.g. auth) override this method.
        """

    # ── Lifecycle ─────────────────────────────────────────────

    async def on_startup(self, app: FastAPI) -> None:
        """Called after all modules are registered, during app startup."""

    async def on_shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""
