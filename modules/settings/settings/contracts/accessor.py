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
from typing import Any, Final

from settings.contracts.registry import SettingsRegistry
from settings.contracts.schemas import (
    SettingOut,
    SettingScope,
    SettingUpsert,
    SettingValueType,
)
from settings.contracts.service import ISettingService

_TRUTHY = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSY = frozenset({"0", "false", "f", "no", "n", "off"})
_UNSET: Final[Any] = object()


class SettingsAccessor:
    """Request-scoped facade over ``ISettingService``.

    Bound to an optional ``user_id`` + ``tenant_id`` so ``get`` and its
    typed variants resolve via USER > TENANT > SYSTEM automatically.
    ``SettingService`` (the implementation) is still reachable for admin
    flows that need unbound operations.
    """

    __slots__ = ("_registry", "_svc", "_tenant_id", "_user_id")

    def __init__(
        self,
        service: ISettingService,
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
    def service(self) -> ISettingService:
        return self._svc

    @property
    def registry(self) -> SettingsRegistry | None:
        return self._registry

    def bind(
        self,
        *,
        user_id: str | None | Any = _UNSET,
        tenant_id: str | None | Any = _UNSET,
    ) -> SettingsAccessor:
        """Return a new accessor with the given user/tenant overrides.

        Pass ``None`` explicitly to clear that side of the context;
        omit the argument to preserve the current value. ``bind()`` with
        no arguments returns a shallow copy bound to the same context.
        """
        return SettingsAccessor(
            self._svc,
            self._registry,
            user_id=self._user_id if user_id is _UNSET else user_id,
            tenant_id=self._tenant_id if tenant_id is _UNSET else tenant_id,
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
        if raw is None:
            return default
        lowered = raw.strip().lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False
        return default

    async def get_int(self, key: str, default: int = 0) -> int:
        raw = await self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    async def get_float(self, key: str, default: float = 0.0) -> float:
        raw = await self.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    async def get_json(self, key: str, default: Any = None) -> Any:
        raw = await self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default

    async def get_typed(self, key: str, default: Any = None) -> Any:
        """Resolve a key and cast based on the stored ``value_type``.

        Picks ``get_bool`` / ``get_int`` / ``get_float`` / ``get_json`` by
        the declared type of the row that wins resolution; falls back to
        a plain string for ``STRING`` or when no row exists. Useful for
        generic admin views that don't know each key's type at compile
        time.
        """
        out = await self._svc.resolve(key, user_id=self._user_id, tenant_id=self._tenant_id)
        if out is None:
            return default
        casters = {
            SettingValueType.BOOL: self._cast_bool,
            SettingValueType.INT: self._cast_int,
            SettingValueType.FLOAT: self._cast_float,
            SettingValueType.JSON: self._cast_json,
        }
        caster = casters.get(out.value_type)
        if caster is None:
            return out.value
        return caster(out.value, default)

    # ── Writes ──────────────────────────────────────────────────────

    async def set_system(
        self,
        key: str,
        value: str,
        value_type: SettingValueType | None = None,
        description: str | None = None,
    ) -> SettingOut:
        from settings.constants import SYSTEM_SCOPE_ID

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

    # ── Cast helpers (shared by get_typed) ──────────────────────────

    @staticmethod
    def _cast_bool(raw: str, default: Any) -> Any:
        lowered = raw.strip().lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False
        return default

    @staticmethod
    def _cast_int(raw: str, default: Any) -> Any:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cast_float(raw: str, default: Any) -> Any:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _cast_json(raw: str, default: Any) -> Any:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default
