"""What a tenant sees of its overridable settings (#382).

One row per ``tenant_overridable`` definition: the value the tenant inherits
(system override, else the declared default), its own override if any, and the
effective value — the same precedence ``SettingsAccessor`` applies at runtime.
Used by the self-service list endpoint and by the tenant settings page.
"""

from __future__ import annotations

from sqlmodel import SQLModel

from settings._secrets import conceals_secret, mask
from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.registry import SettingsRegistry
from settings.contracts.schemas import SettingScope, SettingValueType
from settings.service import SettingService


class TenantSettingView(SQLModel):
    """One overridable key, as the active tenant sees it."""

    key: str
    description: str
    value_type: SettingValueType
    inherited: str
    """What applies without a tenant override: the system value, else the default."""
    value: str | None
    """The tenant's own override, ``None`` while it inherits."""
    effective: str
    upload_url: str = ""
    """Set for a file-id key: upload here (POST) / clear here (DELETE)."""
    description_key: str = ""
    """i18n key for ``description``; the client falls back to ``description``."""


def _shown(key: str, value: str | None, value_type: str) -> str | None:
    if value is None:
        return None
    return mask(value) if conceals_secret(key, value, value_type) else value


async def list_for_tenant(
    service: SettingService, registry: SettingsRegistry | None, tenant_id: str
) -> list[TenantSettingView]:
    if registry is None:
        return []
    definitions = registry.tenant_overridable
    if not definitions:
        return []
    keys = {d.key for d in definitions}
    system = {
        row.key: row.value
        for row in await service.list_by_scope_unmasked(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        if row.key in keys
    }
    own = {
        row.key: row.value
        for row in await service.list_by_scope_unmasked(SettingScope.TENANT, tenant_id)
        if row.key in keys
    }
    views = []
    for d in definitions:
        inherited = system.get(d.key, d.default)
        value = own.get(d.key)
        views.append(
            TenantSettingView(
                key=d.key,
                description=d.description,
                value_type=d.value_type,
                inherited=_shown(d.key, inherited, d.value_type) or "",
                value=_shown(d.key, value, d.value_type),
                effective=_shown(d.key, value if value is not None else inherited, d.value_type)
                or "",
                upload_url=d.upload_url,
                description_key=d.description_key,
            )
        )
    return views


__all__ = ["TenantSettingView", "list_for_tenant"]
