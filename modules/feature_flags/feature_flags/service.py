"""FeatureFlagService — manages persisted overrides and syncs them to the registry."""

from __future__ import annotations

from simple_module_core.feature_flags import FeatureFlagRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_flags.contracts.schemas import FeatureFlagOverrideOut, FeatureFlagView
from feature_flags.models import FeatureFlagOverride


class FeatureFlagService:
    """Read/write persisted overrides and keep the in-memory registry in sync.

    The registry is the source of truth for *which* flags exist and their
    defaults — those come from module code. This service owns the persisted
    overrides: anything an admin toggles in the UI is written here and
    mirrored to ``registry._overrides`` so ``is_enabled`` returns the right
    value for subsequent requests.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_overrides(self) -> list[FeatureFlagOverrideOut]:
        result = await self.db.execute(
            select(FeatureFlagOverride).order_by(FeatureFlagOverride.name)
        )
        return [FeatureFlagOverrideOut.model_validate(row) for row in result.scalars()]

    async def _get_by_name(self, name: str) -> FeatureFlagOverride | None:
        result = await self.db.execute(
            select(FeatureFlagOverride).where(FeatureFlagOverride.name == name)
        )
        return result.scalar_one_or_none()

    async def list_flags(self, registry: FeatureFlagRegistry) -> list[FeatureFlagView]:
        """Join registered definitions with persisted overrides for admin display.

        Definitions the registry doesn't know about are silently dropped — an
        override whose flag was removed from code is stale and should be
        cleared rather than surfaced as a "ghost" row.
        """
        overrides = {o.name: o.enabled for o in await self.list_overrides()}
        views: list[FeatureFlagView] = []
        for flag in sorted(registry.all_flags, key=lambda f: f.name):
            overridden = flag.name in overrides
            effective = overrides[flag.name] if overridden else flag.default_enabled
            views.append(
                FeatureFlagView(
                    name=flag.name,
                    description=flag.description,
                    default_enabled=flag.default_enabled,
                    enabled=effective,
                    overridden=overridden,
                )
            )
        return views

    async def set_override(
        self,
        name: str,
        enabled: bool,
        registry: FeatureFlagRegistry | None = None,
    ) -> FeatureFlagOverrideOut:
        """Upsert an override and (optionally) mirror it to the in-memory registry."""
        existing = await self._get_by_name(name)
        if existing is None:
            existing = FeatureFlagOverride(name=name, enabled=enabled)
            self.db.add(existing)
        else:
            existing.enabled = enabled
        await self.db.flush()
        await self.db.refresh(existing)
        if registry is not None:
            registry.set_override(name, enabled)
        return FeatureFlagOverrideOut.model_validate(existing)

    async def clear_override(
        self,
        name: str,
        registry: FeatureFlagRegistry | None = None,
    ) -> bool:
        """Delete an override and revert the registry to the flag's default."""
        existing = await self._get_by_name(name)
        if existing is None:
            return False
        await self.db.delete(existing)
        if registry is not None:
            registry.clear_override(name)
        return True

    async def hydrate_registry(self, registry: FeatureFlagRegistry) -> int:
        """Load every persisted override into the registry. Called once at boot."""
        overrides = await self.list_overrides()
        for ovr in overrides:
            registry.set_override(ovr.name, ovr.enabled)
        return len(overrides)
