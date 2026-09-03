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

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from inertia import InertiaConfig
    from simple_module_db.session import DatabaseState
    from simple_module_hosting.settings import Settings

    from simple_module_core.audit_links import AuditLinkRegistry
    from simple_module_core.design_packs import DesignPackRegistry
    from simple_module_core.diagnostics import Diagnostic
    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.i18n import I18nRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.module import ModuleBase
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_core.public_routes import PublicRouteRegistry
    from simple_module_core.setup_steps import SetupRegistry


@dataclass(slots=True)
class DiagnosticsState:
    """The boot diagnostics run, kept so something can read it later.

    The one deliberately *mutable* member of :class:`Services`. ``create_app``
    ran the checks, printed them and dropped the list, which left the in-app
    Doctor screen with nothing real to render — and re-running a full AST sweep
    of the source tree per request is not an option.

    ``runner`` is ``None`` outside development, where the checks never run at
    all: several of them read the source tree, which a deployed wheel does not
    ship. A reader must show "not available here" rather than an empty, and
    therefore clean-looking, result.
    """

    #: Re-invokes the exact ``run_diagnostics(...)`` call the builder made.
    runner: Callable[[], list[Diagnostic]] | None = None
    results: list[Diagnostic] = field(default_factory=list)
    #: When ``results`` was produced; ``None`` until the first run.
    ran_at: datetime | None = None

    @property
    def supported(self) -> bool:
        """Whether these checks can run in this environment at all."""
        return self.runner is not None

    def rerun(self) -> list[Diagnostic]:
        """Run the checks again, replacing ``results``. A no-op when unsupported."""
        if self.runner is None:
            return []
        self.results = self.runner()
        self.ran_at = datetime.now(UTC)
        return self.results


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
    public_routes: PublicRouteRegistry
    setup_registry: SetupRegistry
    design_packs: DesignPackRegistry
    audit_links: AuditLinkRegistry
    i18n_registry: I18nRegistry
    inertia_config: InertiaConfig
    modules: tuple[ModuleBase, ...]
    #: Defaulted so an app built outside ``create_app`` still has a holder to
    #: read; that one simply reports the checks as unsupported.
    diagnostics: DiagnosticsState = field(default_factory=DiagnosticsState)
