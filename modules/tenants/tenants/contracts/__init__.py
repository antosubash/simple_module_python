"""Public contracts of the Tenants module."""

from tenants.contracts.entitlements import (
    EntitlementExceededError,
    EntitlementProvider,
    UnlimitedEntitlements,
    ensure_within_limit,
)

__all__ = [
    "EntitlementExceededError",
    "EntitlementProvider",
    "UnlimitedEntitlements",
    "ensure_within_limit",
]
