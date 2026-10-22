"""Module lifecycle base class. ``ModuleMeta`` lives in ``module_meta``."""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core._request_hooks import RequestHooksMixin
from simple_module_core.module_meta import ModuleMeta

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from simple_module_core.audit_links import AuditLinkRegistry
    from simple_module_core.design_packs import DesignPackRegistry
    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.invalidation import InvalidationBus
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_core.resources import ResourceTypeRegistry
    from simple_module_core.setup_steps import SetupRegistry
    from simple_module_core.spa_mount import SpaMount


class ModuleBase(RequestHooksMixin, ABC):
    """Base class for all modules.

    Subclasses override only the methods they need; every hook is a no-op by
    default. Request-pipeline hooks (public routes, body limits, CSP sources,
    CORS policies, rate limits, middleware, exception handlers) live in
    ``_request_hooks.RequestHooksMixin``. The boot order the host calls them
    in is documented in ``docs/framework/lifecycle.md`` (settings, then the
    declarative registrations in ``_registrations.run_module_registrations``,
    then database, Inertia, middleware, routes, and finally ``on_startup``).
    """

    meta: ModuleMeta

    def register_settings(self, app: FastAPI) -> None:
        """Load module-specific settings and store on ``app.state``.

        Called before all other registration hooks.
        """

    # ── Service Registration ──────────────────────────────────

    def register_routes(
        self,
        api_router: APIRouter,
        view_router: APIRouter,
    ) -> None:
        """Register API endpoints and Inertia view routes."""

    def register_admin_routes(self, admin_router: APIRouter) -> None:
        """Register admin-only view routes, mounted at ``meta.admin_view_prefix``.

        Only for modules serving both public and admin pages (see
        ``ModuleMeta.admin_view_prefix``); all-admin modules point
        ``view_prefix`` at ``/admin/...``. Nothing is gated automatically:
        the prefix is a URL convention, not a permission.
        """

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

    def register_invalidations(self, bus: InvalidationBus, app: FastAPI) -> None:
        """Subscribe this module's per-process caches to their channels.

        Handlers may only *forget* (drop a cache entry); the bus has no
        delivery guarantee, so a database write would repeat unpredictably::

            def register_invalidations(self, bus, app):
                bus.subscribe("orders.totals", lambda inv: _TOTALS.pop(inv.key, None))

        Publishing needs no hook — reach the same bus at
        ``request.app.state.sm.invalidation`` from a ``db.on_commit`` callback.
        Cross-process delivery depends on a transport being installed, so every
        cache keeps its TTL as a floor. See ``docs/framework/invalidation.md``.
        """

    def register_health_checks(self, registry: HealthRegistry) -> None:
        """Contribute health checks for the ``/health/ready`` endpoint."""

    def register_setup_steps(self, registry: SetupRegistry) -> None:
        """Declare what this module needs before the install is usable.

        While any required step reports incomplete, ``SetupMiddleware`` serves
        the first-run wizard instead of the app::

            registry.add(SetupStep(id="users.administrator", ...))

        A module that registers nothing never gates the app — that is how an
        external identity provider opts out. See docs/module-authoring.md.

        Called once at boot, in dependency order.
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

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        """Declare where this module's audited records can be viewed.

        An audit entry stores a model class name and a primary key, which
        tells the reader what changed but gives them no way to open it.
        Override this hook to make your module's rows reachable from the audit
        log::

            def register_audit_links(self, registry):
                registry.register(
                    AuditLink.for_model(
                        User,
                        url_template="/admin/users/{id}/edit",
                        label="User",
                    )
                )

        ``entity_type`` is the **model class name** the rows are audited under
        (``"User"``), not the ``__tablename__`` (``"users_user"``):
        ``snapshot_changes`` records ``type(obj).__name__``, so a table-name
        key silently never matches.
        Registering only supplies the URL — the target route still enforces
        its own permissions, so linking never widens access. Called once at
        boot, in dependency order.
        """

    def register_resource_types(self, registry: ResourceTypeRegistry) -> None:
        """Declare resource types whose rows carry object-level access (GH #526).

        ``registry.register(ResourceType(name="notes.note", policy=...,
        select_by_id=...))`` makes the type's :class:`ResourcePolicy` reachable
        by cross-cutting code such as the ``sharing`` module. Names are dotted
        and unique; a duplicate raises at boot. See
        ``docs/framework/resource-access.md``.
        """

    # ── Asset contribution (templates & static files) ─────────

    def template_dirs(self) -> list[Path]:
        """Return Jinja2 template directories this module contributes.

        The host aggregates all modules' template dirs (plus its own) into the
        Jinja2 loader, so templates in ``<module>/templates/`` become resolvable
        from any module. Return an empty list (default) to contribute none.

        Typically ``importlib.resources.files(__package__) / "templates"``.
        """
        return []

    def static_mounts(self) -> dict[str, Path]:
        """Return static file mounts this module contributes.

        Mapping of URL prefix → directory, mounted via ``StaticFiles`` at boot.
        Convention: prefix with ``/modules/<name>/static``. Default: none.
        """
        return {}

    def spa_mounts(self) -> list[SpaMount]:
        """Return legacy client-routed SPAs to serve under a URL prefix.

        Served from ``dist_dir`` with an ``index.html`` deep-link fallback and
        excluded from Inertia link interception. See ``docs/framework/spa-mounts.md``.
        """
        return []

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

    def db_extensions(self) -> list[str]:
        """Postgres extensions this module needs (``["ltree", "pg_trgm"]``).

        Names match ``^[a-z][a-z0-9_-]*$``. ``ensure_db_extensions`` creates them
        before migrations run; on SQLite that raises (doctor SM029 warns early).
        """
        return []

    # ── Lifecycle ─────────────────────────────────────────────

    async def on_startup(self, app: FastAPI) -> None:
        """Called after all modules are registered, during app startup."""

    async def on_shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""


__all__ = ["ModuleBase", "ModuleMeta"]
