"""Module metadata — the declarative half of a module definition.

Split from ``module.py`` so that file holds only the lifecycle base class.
``ModuleMeta`` is what a module *declares* about itself (name, mount
points, dependencies, compatibility); ``ModuleBase`` is what it *does*.
They change for different reasons and are read by different callers —
discovery reads the metadata, the host invokes the hooks.

Re-exported from ``module.py``, so every existing import still works.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModuleMeta:
    """Metadata describing a module."""

    name: str
    route_prefix: str = ""
    view_prefix: str = ""
    admin_view_prefix: str = ""
    """Mount point for admin-only view routes, e.g. ``"/admin/users"``.

    A module gets exactly one ``view_prefix``, which is a problem for modules
    that are only *partly* administrative: ``users`` serves ``/users/login``
    and the user-management CRUD from the same package, and those belong in
    different places in the URL space. Declaring this gives such a module a
    second view router mounted here, populated by ``register_admin_routes``.

    Modules that are administrative end to end don't need it — they just point
    ``view_prefix`` at ``/admin/...`` directly.
    """
    depends_on: list[str] = field(default_factory=list)
    """Modules this one needs. Outside development a missing one refuses the
    boot (``MissingDependencyError``, GH #501); in development it is logged."""
    optional_depends_on: list[str] = field(default_factory=list)
    """Modules to sort after **when they are loaded**; absence is fine.

    For an ordering-only relationship — subscribe after the module that
    publishes an event, wrap middleware outside another's — where the module
    works without the other one. Sorted exactly like ``depends_on`` when
    present, so moving an entry here does not change the boot order.
    """
    version: str = "1.0.0"
    requires_framework: str | None = None
    """PEP 440 specifier for the framework API version this module supports.

    Example: ``">=1.0,<2.0"``. When set, the module is rejected at boot if the
    installed ``simple_module_core.FRAMEWORK_API_VERSION`` does not satisfy it.
    When ``None``, no compatibility check is performed (legacy modules);
    this bypass is deprecated with ``remove_in="0.1.0"`` (tracked by the
    deprecation-expiry test; it does not warn at boot).
    """
    i18n_audience: str = "public"
    """Who this module's locale catalog is shipped to: ``"public"`` or ``"admin"``.

    ``"public"`` (the default) ships the catalog in every Inertia payload.
    ``"admin"`` ships it only to authenticated users — declare it on modules
    whose UI sits entirely behind login (settings, permissions, dashboards) so
    anonymous visitors don't download admin form labels on every public page.
    The catalog is always available server-side (``Translator``) either way.
    """
