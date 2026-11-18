"""App-free principal providers; modules own the stores, core owns resolution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from simple_module_core.permissions import PermissionRegistry
from simple_module_core.user_directory import NullUserDirectory, UserDirectory

PRINCIPALS_KEY = "sm_principals"

MembershipRole = Callable[[Any, str, str], Awaitable[str | None]]
TenantActive = Callable[[Any, str], Awaitable[bool]]
RoleOverlays = Callable[[Any, list[str] | None], Awaitable[dict[str, list[str]]]]


@dataclass
class PrincipalRegistry:
    """Providers installed by ``register_principal_builder``, without an app.

    A missing directory knows nobody; a missing membership provider admits nobody
    on a multi-tenant host. Provider/database failures propagate to the caller.
    """

    permissions: PermissionRegistry = field(default_factory=PermissionRegistry)
    directory: UserDirectory = field(default_factory=NullUserDirectory)
    membership_role: MembershipRole | None = None
    tenant_active: TenantActive | None = None
    role_overlays: RoleOverlays | None = None
    multi_tenant: bool = False
    default_tenant: str | None = None


def build_principal_registry(
    modules: Sequence[Any],
    settings: Any,
    *,
    permissions: PermissionRegistry | None = None,
) -> PrincipalRegistry:
    """Register providers from the host's already selected and ordered modules.

    Workers also register permission declarations here; a host supplies its
    existing permission registry to avoid registering grant sources twice.
    No settings/startup hooks, FastAPI instance or network services are built.
    """
    registry = PrincipalRegistry(
        permissions=permissions if permissions is not None else PermissionRegistry(),
        multi_tenant=settings.multi_tenant,
        default_tenant=settings.default_tenant or None,
    )
    for module in modules:
        if permissions is None:
            module.register_permissions(registry.permissions)
        module.register_principal_builder(registry)
    return registry
