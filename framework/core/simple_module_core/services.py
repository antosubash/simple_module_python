"""Framework-scoped singleton container.

Stored as ``app.state.sm`` during :func:`create_app`. Consumers read
``request.app.state.sm.<field>`` instead of reaching for loose
``app.state`` attributes — gives us typing, discoverability, and a
single place to see what the framework owns.

Frozen + slotted by design: Services is built once at boot and never
mutated. Slots reject attribute additions, which is how the previous
``app.state`` shape grew unbounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inertia import InertiaConfig
    from simple_module_db.session import DatabaseState
    from simple_module_hosting.settings import Settings

    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.i18n import I18nRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.module import ModuleBase
    from simple_module_core.permissions import PermissionRegistry


@dataclass(frozen=True, slots=True)
class Services:
    """Framework singletons. One slot per owner, read-only after boot."""

    settings: Settings
    db: DatabaseState
    event_bus: EventBus
    menu_registry: MenuRegistry
    permissions: PermissionRegistry
    feature_flags: FeatureFlagRegistry
    health_registry: HealthRegistry
    i18n_registry: I18nRegistry
    inertia_config: InertiaConfig
    modules: tuple[ModuleBase, ...]
