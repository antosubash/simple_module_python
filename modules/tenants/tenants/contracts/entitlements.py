"""Entitlements — the seam a billing module plugs its plans into.

Consumers ask *what a tenant may do* without knowing why: a plan, a trial, a
manual override. ``tenants`` ships :class:`UnlimitedEntitlements`, so an
install without billing has no limits. A billing module replaces it::

    app.state.tenants.entitlements = PlanEntitlements(...)

Consumers depend on this protocol, never on the billing module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EntitlementProvider(Protocol):
    async def limit(self, tenant_id: str, key: str) -> int | None:
        """Maximum allowed for ``key`` (e.g. ``tenants.seats``); ``None`` = unlimited."""
        ...

    async def has_feature(self, tenant_id: str, key: str) -> bool:
        """Whether the tenant's plan includes a feature."""
        ...


class UnlimitedEntitlements:
    """Default provider: no limits, every feature. Used until billing is installed."""

    async def limit(self, tenant_id: str, key: str) -> int | None:
        return None

    async def has_feature(self, tenant_id: str, key: str) -> bool:
        return True


class EntitlementExceededError(Exception):
    """A tenant hit a plan limit. Mapped to HTTP 402 by the module."""

    def __init__(self, key: str, limit: int) -> None:
        super().__init__(f"Plan limit reached for '{key}' ({limit})")
        self.key = key
        self.limit = limit


async def ensure_within_limit(
    provider: EntitlementProvider, tenant_id: str, key: str, current: int, adding: int = 1
) -> None:
    """Raise :class:`EntitlementExceededError` if ``current + adding`` would exceed the limit."""
    limit = await provider.limit(tenant_id, key)
    if limit is not None and current + adding > limit:
        raise EntitlementExceededError(key, limit)
