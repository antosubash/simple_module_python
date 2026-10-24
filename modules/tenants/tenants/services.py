"""Module-scoped state container, stored as ``app.state.tenants``."""

from __future__ import annotations

from dataclasses import dataclass, field

from tenants.contracts.entitlements import EntitlementProvider, UnlimitedEntitlements
from tenants.contracts.usage import UnlimitedUsageMeter, UsageMeter
from tenants.settings import TenantsSettings


@dataclass
class TenantsServices:
    """Tenants module singletons.

    ``entitlements`` is the billing seam: a billing module assigns its own
    :class:`EntitlementProvider` here during its ``on_startup``.
    ``usage`` similarly accepts a billing module's :class:`UsageMeter`.
    """

    settings: TenantsSettings
    entitlements: EntitlementProvider = field(default_factory=UnlimitedEntitlements)
    usage: UsageMeter = field(default_factory=UnlimitedUsageMeter)
