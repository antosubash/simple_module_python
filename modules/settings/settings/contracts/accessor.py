"""High-level read/write facade over ``SettingService`` for consumer modules.

Consumers depend on this instead of ``SettingService`` directly so they get:
- automatic USER > TENANT > SYSTEM resolution bound to the request context,
- typed getters (`get_bool`, `get_int`, `get_float`, `get_json`) that cast
  the stored string representation,
- fallback to the registered default in ``SettingsRegistry`` when a key is
  unset at every scope.

Example in another module's endpoint:

    from settings.contracts import SettingsDep

    @router.get("/whatever")
    async def handler(settings: SettingsDep):
        if await settings.get_bool("orders.bulk_import", default=False):
            ...
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.registry import SettingsRegistry
from settings.contracts.schemas import (
    BOOL_LITERALS_FALSE,
    BOOL_LITERALS_TRUE,
    SettingOut,
    SettingScope,
    SettingUpsert,
    SettingValueType,
)

if TYPE_CHECKING:
    from settings.service import SettingService


class _Unset:
    """Typed sentinel for ``bind``'s "no override" marker."""


_UNSET: Final = _Unset()


def _cast_bool(raw: str, default: Any) -> Any:
    lowered = raw.strip().lower()
    if lowered in BOOL_LITERALS_TRUE:
        return True
    if lowered in BOOL_LITERALS_FALSE:
        return False
    return default


def _cast_int(raw: str, default: Any) -> Any:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _cast_float(raw: str, default: Any) -> Any:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _cast_json(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


_CASTERS: Final[dict[SettingValueType, Callable[[str, Any], Any]]] = {
    SettingValueType.BOOL: _cast_bool,
    SettingValueType.INT: _cast_int,
    SettingValueType.FLOAT: _cast_float,
    SettingValueType.JSON: _cast_json,
}


class SettingsAccessor:
    """Request-scoped facade over ``SettingService``.

    Bound to an optional ``user_id`` + ``tenant_id`` so ``get`` and its
    typed variants resolve via USER > TENANT > SYSTEM automatically.
    ``SettingService`` (the implementation) is still reachable for admin
    flows that need unbound operations.
    """

    __slots__ = ("_registry", "_svc", "_tenant_id", "_user_id")

    def __init__(
        self,
        service: SettingService,
        registry: SettingsRegistry | None = None,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self._svc = service
        self._registry = registry
        self._user_id = user_id
        self._tenant_id = tenant_id

    @property
    def service(self) -> SettingService:
        return self._svc

    @property
    def registry(self) -> SettingsRegistry | None:
        return self._registry

    def bind(
        self,
        *,
        user_id: str | _Unset | None = _UNSET,
        tenant_id: str | _Unset | None = _UNSET,
    ) -> SettingsAccessor:
        """Return a new accessor with the given user/tenant overrides.

        Pass ``None`` explicitly to clear that side of the context;
        omit the argument to preserve the current value. ``bind()`` with
        no arguments returns a shallow copy bound to the same context.
        """
        return SettingsAccessor(
            self._svc,
            self._registry,
            user_id=self._user_id if isinstance(user_id, _Unset) else user_id,
            tenant_id=self._tenant_id if isinstance(tenant_id, _Unset) else tenant_id,
        )

    # ── Typed reads ─────────────────────────────────────────────────

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Resolve a key as a string, walking USER > TENANT > SYSTEM.

        Falls back to the explicit ``default`` argument, then the
        registered default in ``SettingsRegistry`` if present.
        """
        value = await self._svc.get_resolved_value(
            key, user_id=self._user_id, tenant_id=self._tenant_id
        )
        if value is not None:
            return value
        if default is not None:
            return default
        if self._registry is not None:
            definition = self._registry.get(key)
            if definition is not None:
                return definition.default
        return None

    async def get_str(self, key: str, default: str = "") -> str:
        value = await self.get(key)
        return value if value is not None else default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        raw = await self.get(key)
        return default if raw is None else _cast_bool(raw, default)

    async def get_int(self, key: str, default: int = 0) -> int:
        raw = await self.get(key)
        return default if raw is None else _cast_int(raw, default)

    async def get_float(self, key: str, default: float = 0.0) -> float:
        raw = await self.get(key)
        return default if raw is None else _cast_float(raw, default)

    async def get_json(self, key: str, default: Any = None) -> Any:
        raw = await self.get(key)
        return default if raw is None else _cast_json(raw, default)

    async def get_typed(self, key: str, default: Any = None) -> Any:
        """Resolve a key and cast based on the stored ``value_type``.

        Dispatches by the declared type of the row that wins resolution;
        falls back to the raw string for ``STRING`` or when no row exists.
        Useful for generic admin views that don't know each key's type at
        compile time.
        """
        out = await self._svc.resolve(key, user_id=self._user_id, tenant_id=self._tenant_id)
        if out is None:
            return default
        caster = _CASTERS.get(out.value_type)
        return out.value if caster is None else caster(out.value, default)

    # ── Writes ──────────────────────────────────────────────────────

    async def set_system(
        self,
        key: str,
        value: str,
        value_type: SettingValueType | None = None,
        description: str | None = None,
    ) -> SettingOut:
        return await self._svc.upsert_scoped(
            SettingScope.SYSTEM,
            SYSTEM_SCOPE_ID,
            key,
            SettingUpsert(value=value, value_type=value_type, description=description),
        )

    async def set_tenant(
        self,
        tenant_id: str,
        key: str,
        value: str,
        value_type: SettingValueType | None = None,
        description: str | None = None,
    ) -> SettingOut:
        return await self._svc.upsert_scoped(
            SettingScope.TENANT,
            tenant_id,
            key,
            SettingUpsert(value=value, value_type=value_type, description=description),
        )

    async def set_user(
        self,
        user_id: str,
        key: str,
        value: str,
        value_type: SettingValueType | None = None,
        description: str | None = None,
    ) -> SettingOut:
        return await self._svc.upsert_scoped(
            SettingScope.USER,
            user_id,
            key,
            SettingUpsert(value=value, value_type=value_type, description=description),
        )
