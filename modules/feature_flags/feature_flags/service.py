"""FeatureFlagService — manages persisted overrides and syncs them to the registry.

Resolution semantics (tenant > system > default) live in
``simple_module_core.feature_flags``; this layer only persists overrides and
mirrors mutations into the registry.
"""

from __future__ import annotations

from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_flags.constants import SCOPE_SYSTEM, SCOPE_TENANT, SYSTEM_SCOPE_ID
from feature_flags.contracts.schemas import FeatureFlagOverrideOut, FeatureFlagView
from feature_flags.models import FeatureFlagOverride


def _registry_tenant_id(scope: str, scope_id: str) -> str | None:
    """Translate a (scope, scope_id) pair into the registry's tenant_id arg."""
    return scope_id if scope == SCOPE_TENANT else None


def _build_view(
    flag: FeatureFlagDefinition,
    *,
    enabled: bool,
    overridden: bool,
    system_enabled: bool | None = None,
) -> FeatureFlagView:
    return FeatureFlagView(
        name=flag.name,
        description=flag.description,
        default_enabled=flag.default_enabled,
        enabled=enabled,
        overridden=overridden,
        system_enabled=system_enabled,
    )


class FeatureFlagService:
    """Read/write persisted overrides and keep the in-memory registry in sync.

    The registry is the source of truth for *which* flags exist and their
    defaults — those come from module code. This service owns the persisted
    overrides at both system and tenant scope, mirroring every mutation back
    into the registry so ``is_enabled`` returns the right value without an
    extra DB hit per request.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_overrides(self) -> list[FeatureFlagOverrideOut]:
        """Every persisted override across all scopes, ordered for stable display."""
        result = await self.db.execute(
            select(FeatureFlagOverride).order_by(
                FeatureFlagOverride.scope,
                FeatureFlagOverride.scope_id,
                FeatureFlagOverride.name,
            )
        )
        return [FeatureFlagOverrideOut.model_validate(row) for row in result.scalars()]

    async def list_tenants_with_overrides(self) -> list[str]:
        """Distinct tenant_ids that have at least one tenant-scope override."""
        result = await self.db.execute(
            select(FeatureFlagOverride.scope_id)
            .where(FeatureFlagOverride.scope == SCOPE_TENANT)
            .distinct()
            .order_by(FeatureFlagOverride.scope_id)
        )
        return list(result.scalars())

    async def list_flags(
        self, registry: FeatureFlagRegistry, tenant_id: str | None = None
    ) -> list[FeatureFlagView]:
        """Join registered definitions with persisted overrides for admin display.

        When ``tenant_id`` is None, the view is system-scoped: ``enabled``
        reflects the system override (or default), and ``overridden`` is
        true when a system row exists. When ``tenant_id`` is set, the view
        is for that tenant: ``enabled`` is the resolved value the tenant
        would see at runtime, ``overridden`` flags whether *this tenant*
        has its own override, and ``system_enabled`` reports the value that
        would apply if the tenant override were cleared.

        Reads override state from the in-memory registry (kept in sync by
        every mutation and rehydrated at startup) rather than re-querying
        the DB, so admin page loads don't pay an O(rows) scan per request.
        """
        views: list[FeatureFlagView] = []
        for flag in sorted(registry.all_flags, key=lambda f: f.name):
            system_value = registry.system_override(flag.name)
            system_enabled = system_value if system_value is not None else flag.default_enabled
            if tenant_id is None:
                views.append(
                    _build_view(flag, enabled=system_enabled, overridden=system_value is not None)
                )
                continue
            tenant_value = registry.tenant_override(flag.name, tenant_id)
            views.append(
                _build_view(
                    flag,
                    enabled=tenant_value if tenant_value is not None else system_enabled,
                    overridden=tenant_value is not None,
                    system_enabled=system_enabled,
                )
            )
        return views

    def build_view(
        self, registry: FeatureFlagRegistry, name: str, tenant_id: str | None = None
    ) -> FeatureFlagView | None:
        """Single-flag variant of ``list_flags`` for write-path responses."""
        flag = next((f for f in registry.all_flags if f.name == name), None)
        if flag is None:
            return None
        system_value = registry.system_override(name)
        system_enabled = system_value if system_value is not None else flag.default_enabled
        if tenant_id is None:
            return _build_view(flag, enabled=system_enabled, overridden=system_value is not None)
        tenant_value = registry.tenant_override(name, tenant_id)
        return _build_view(
            flag,
            enabled=tenant_value if tenant_value is not None else system_enabled,
            overridden=tenant_value is not None,
            system_enabled=system_enabled,
        )

    async def _find(self, scope: str, scope_id: str, name: str) -> FeatureFlagOverride | None:
        result = await self.db.execute(
            select(FeatureFlagOverride).where(
                FeatureFlagOverride.scope == scope,
                FeatureFlagOverride.scope_id == scope_id,
                FeatureFlagOverride.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def set_override(
        self,
        name: str,
        enabled: bool,
        registry: FeatureFlagRegistry | None = None,
        scope: str = SCOPE_SYSTEM,
        scope_id: str = SYSTEM_SCOPE_ID,
    ) -> FeatureFlagOverrideOut:
        """Upsert an override at the given scope and mirror it to the registry."""
        existing = await self._find(scope, scope_id, name)
        if existing is None:
            existing = FeatureFlagOverride(
                scope=scope, scope_id=scope_id, name=name, enabled=enabled
            )
            self.db.add(existing)
            await self.db.flush()
        elif existing.enabled != enabled:
            existing.enabled = enabled
            await self.db.flush()
        if registry is not None:
            registry.set_override(name, enabled, tenant_id=_registry_tenant_id(scope, scope_id))
        return FeatureFlagOverrideOut.model_validate(existing)

    async def clear_override(
        self,
        name: str,
        registry: FeatureFlagRegistry | None = None,
        scope: str = SCOPE_SYSTEM,
        scope_id: str = SYSTEM_SCOPE_ID,
    ) -> bool:
        """Delete the override at the given scope and revert the registry layer."""
        existing = await self._find(scope, scope_id, name)
        if existing is None:
            return False
        await self.db.delete(existing)
        if registry is not None:
            registry.clear_override(name, tenant_id=_registry_tenant_id(scope, scope_id))
        return True

    async def hydrate_registry(self, registry: FeatureFlagRegistry) -> int:
        """Load every persisted override (system + tenant) into the registry at boot."""
        overrides = await self.list_overrides()
        for ovr in overrides:
            registry.set_override(
                ovr.name,
                ovr.enabled,
                tenant_id=_registry_tenant_id(ovr.scope, ovr.scope_id),
            )
        return len(overrides)
