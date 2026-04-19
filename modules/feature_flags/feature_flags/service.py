"""FeatureFlagService — manages persisted overrides and syncs them to the registry.

Two scopes are supported:

* **system** — applied to every request (mirrored to the registry's
  system override map at write time)
* **tenant** — applied only when ``is_enabled`` is called with a matching
  ``tenant_id`` (mirrored to the per-tenant override map)

Resolution at runtime: tenant override > system override > definition default.
"""

from __future__ import annotations

from simple_module_core.feature_flags import FeatureFlagRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_flags.constants import SCOPE_SYSTEM, SCOPE_TENANT, SYSTEM_SCOPE_ID
from feature_flags.contracts.schemas import FeatureFlagOverrideOut, FeatureFlagView
from feature_flags.models import FeatureFlagOverride


def _registry_tenant_id(scope: str, scope_id: str) -> str | None:
    """Translate a (scope, scope_id) pair into the registry's tenant_id arg."""
    return scope_id if scope == SCOPE_TENANT else None


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

    # ── Listing ─────────────────────────────────────────────────────

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

        Definitions the registry doesn't know about are silently dropped —
        an override whose flag was removed from code is stale and shouldn't
        leak into the admin list as a ghost entry.
        """
        rows = await self.list_overrides()
        system_overrides: dict[str, bool] = {
            row.name: row.enabled
            for row in rows
            if row.scope == SCOPE_SYSTEM and row.scope_id == SYSTEM_SCOPE_ID
        }
        tenant_overrides: dict[str, bool] = (
            {
                row.name: row.enabled
                for row in rows
                if row.scope == SCOPE_TENANT and row.scope_id == tenant_id
            }
            if tenant_id is not None
            else {}
        )

        views: list[FeatureFlagView] = []
        for flag in sorted(registry.all_flags, key=lambda f: f.name):
            system_enabled = system_overrides.get(flag.name, flag.default_enabled)
            if tenant_id is None:
                views.append(
                    FeatureFlagView(
                        name=flag.name,
                        description=flag.description,
                        default_enabled=flag.default_enabled,
                        enabled=system_enabled,
                        overridden=flag.name in system_overrides,
                    )
                )
                continue
            has_tenant = flag.name in tenant_overrides
            effective = tenant_overrides[flag.name] if has_tenant else system_enabled
            views.append(
                FeatureFlagView(
                    name=flag.name,
                    description=flag.description,
                    default_enabled=flag.default_enabled,
                    enabled=effective,
                    overridden=has_tenant,
                    system_enabled=system_enabled,
                )
            )
        return views

    # ── Internals ───────────────────────────────────────────────────

    async def _find(self, scope: str, scope_id: str, name: str) -> FeatureFlagOverride | None:
        result = await self.db.execute(
            select(FeatureFlagOverride).where(
                FeatureFlagOverride.scope == scope,
                FeatureFlagOverride.scope_id == scope_id,
                FeatureFlagOverride.name == name,
            )
        )
        return result.scalar_one_or_none()

    # ── Mutations ───────────────────────────────────────────────────

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
        else:
            existing.enabled = enabled
        await self.db.flush()
        await self.db.refresh(existing)
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
