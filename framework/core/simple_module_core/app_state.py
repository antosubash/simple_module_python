"""Typed reads of optional app services, preserving absent-state fallbacks.

Concrete hosting types are imported only for type checking, as in Services:
core stays usable without hosting or any plugin installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from asyncio import Lock
    from collections.abc import Callable

    from simple_module_hosting._host_services import _HostServices
    from simple_module_hosting._tenant import TenantResolver
    from simple_module_hosting.middleware import PrincipalSerializer
    from simple_module_hosting.shared_props import SharedPropsProvider
    from simple_module_inertia import Inertia
    from starlette.requests import Request

    from simple_module_core.body_limits import BodyLimitRegistry
    from simple_module_core.design_packs import DesignPackRegistry
    from simple_module_core.module import ModuleBase
    from simple_module_core.public_routes import PublicRouteRegistry
    from simple_module_core.rate_limit import RateLimitRegistry
    from simple_module_core.services import Services
    from simple_module_core.tenancy import TenantExists, TenantMembers


#: Attribute ``register_inertia_shared_provider`` writes and the renderer reads.
INERTIA_SHARED_PROVIDERS_STATE_ATTR = "inertia_shared_providers"


class AuthProvider(Protocol):
    """Framework-facing auth extension; installed by users or keycloak."""

    async def resolve_user(self, request: Request) -> Any: ...

    def get_login_url(self, request: Request, next_url: str | None = None) -> str: ...


class BrandingState(Protocol):
    """Optional branding services consumed by the document renderer."""

    @property
    def settings(self) -> object: ...

    @property
    def favicon_url(self) -> str | None: ...


def get_auth_provider(app: Any) -> AuthProvider | None:
    """Auth.register_settings installs auth; users/keycloak install its provider."""
    return getattr(getattr(app.state, "auth", None), "auth_provider", None)


def get_services(app: Any) -> Services | None:
    """create_app installs the framework service container.

    Returns None when absent.
    """
    return getattr(getattr(app, "state", None), "sm", None)


def get_host_services(app: Any) -> _HostServices | None:
    """Host settings registration installs the host service container.

    Returns None when absent.
    """
    return getattr(app.state, "host", None)


def get_public_routes(app: Any) -> PublicRouteRegistry | None:
    """create_app installs the public-route registry.

    Returns None when absent.
    """
    return getattr(app.state, "public_routes", None)


def get_body_limits(app: Any) -> BodyLimitRegistry | None:
    """create_app installs the request-body limit registry.

    Returns None when absent.
    """
    return getattr(app.state, "body_limits", None)


def get_rate_limit_rules(app: Any) -> RateLimitRegistry | None:
    """create_app installs the per-route rate-limit registry.

    Returns None when absent.
    """
    return getattr(app.state, "rate_limit_rules", None)


def get_design_packs(app: Any) -> DesignPackRegistry | None:
    """create_app installs the design-pack registry.

    Returns None when absent.
    """
    return getattr(app.state, "design_packs", None)


def get_migration_status(app: Any) -> dict[str, Any] | None:
    """The hosting lifespan and setup wizard install the migration snapshot.

    Returns None when absent.
    """
    return getattr(app.state, "migration", None)


def get_openapi_url(app: Any) -> str | None:
    """Hosting boot records the served OpenAPI URL, or None when disabled.

    Returns None when absent.
    """
    return getattr(app.state, "openapi_url", None)


def get_spa_prefixes(app: Any) -> tuple[str, ...]:
    """SPA mounting records the mounted prefixes; absent means no mounts.

    Returns () when absent.
    """
    return getattr(app.state, "spa_prefixes", ())


def get_deferred_startup(app: Any) -> list[ModuleBase] | None:
    """The hosting lifespan records modules awaiting migrations.

    Returns None when absent.
    """
    return getattr(app.state, "deferred_startup", None)


def get_deferred_startup_lock(app: Any) -> Lock | None:
    """Deferred startup replay lazily installs its per-app lock.

    Returns None when absent.
    """
    return getattr(app.state, "deferred_startup_lock", None)


def get_principal_serializer(app: Any) -> PrincipalSerializer | None:
    """The auth module installs the principal-to-Inertia serializer.

    Returns None when absent.
    """
    return getattr(app.state, "principal_serializer", None)


def get_tenant_resolver(app: Any) -> TenantResolver | None:
    """The tenants module installs request tenant resolution.

    Returns None when absent.
    """
    return getattr(getattr(app, "state", None), "tenant_resolver", None)


def get_tenant_exists(app: Any) -> TenantExists | None:
    """The tenants module installs the tenant-existence callback.

    Returns None when absent.
    """
    return getattr(app.state, "tenant_exists", None)


def get_tenant_members(app: Any) -> TenantMembers | None:
    """The tenants module installs the membership lookup callback.

    Returns None when absent.
    """
    return getattr(app.state, "tenant_members", None)


def get_inertia_dependency(app: Any) -> Callable[..., Inertia] | None:
    """Hosting Inertia setup installs the configured dependency factory.

    Returns None when absent.
    """
    return getattr(app.state, "inertia_dependency", None)


def get_inertia_shared_providers(app: Any) -> list[SharedPropsProvider] | None:
    """register_inertia_shared_provider lazily installs the provider list.

    Returns None when absent.
    """
    return getattr(app.state, INERTIA_SHARED_PROVIDERS_STATE_ATTR, None)


def get_branding(app: Any) -> BrandingState | None:
    """The branding module installs the optional application theme services.

    Returns None when absent.
    """
    return getattr(app.state, "branding", None)
