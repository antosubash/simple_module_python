"""FeatureFlag service protocol — the public contract other modules depend on."""

from __future__ import annotations

from typing import Protocol

from simple_module_core.feature_flags import FeatureFlagRegistry

from feature_flags.contracts.schemas import FeatureFlagOverrideOut, FeatureFlagView


class IFeatureFlagService(Protocol):
    """Interface for feature-flag management operations."""

    async def list_overrides(self) -> list[FeatureFlagOverrideOut]: ...
    async def list_flags(self, registry: FeatureFlagRegistry) -> list[FeatureFlagView]: ...
    async def set_override(self, name: str, enabled: bool) -> FeatureFlagOverrideOut: ...
    async def clear_override(self, name: str) -> bool: ...
    async def hydrate_registry(self, registry: FeatureFlagRegistry) -> int: ...
