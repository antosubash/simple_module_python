"""DB-backed key/value store for module settings (SYSTEM scope).

Wraps the existing SettingService. Keys are namespaced ``<package>.<field>``
to avoid collision with free-form user-defined setting keys.
"""

from __future__ import annotations

from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.schemas import SettingScope, SettingUpsert, SettingValueType
from settings.service import SettingService


def _key(package: str, field: str) -> str:
    return f"{package}.{field}"


class SettingsStore:
    """SYSTEM-scoped key/value store keyed by ``(package, field)``."""

    def __init__(self, service: SettingService) -> None:
        self._service = service

    async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]:
        """Return ``{field_name: (raw_value, value_type)}`` for a package."""
        prefix = f"{package}."
        items = await self._service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        out: dict[str, tuple[str, str]] = {}
        for item in items:
            if not item.key.startswith(prefix):
                continue
            field_name = item.key[len(prefix) :]
            if "." in field_name:
                continue
            out[field_name] = (item.value, item.value_type)
        return out

    async def all_override_fields(self) -> dict[str, frozenset[str]]:
        """Return ``{package: {field_name, ...}}`` for every stored override.

        One query for the whole screen. ``get_overrides`` re-reads the entire
        SYSTEM scope per package, so calling it in a loop over the installed
        modules is one full read per module for the same rows.
        """
        items = await self._service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        out: dict[str, set[str]] = {}
        for item in items:
            package, sep, field_name = item.key.partition(".")
            if not sep or not field_name or "." in field_name:
                continue
            out.setdefault(package, set()).add(field_name)
        return {package: frozenset(fields) for package, fields in out.items()}

    async def set_override(self, package: str, field: str, value: str, value_type: str) -> None:
        await self._service.upsert_scoped(
            SettingScope.SYSTEM,
            SYSTEM_SCOPE_ID,
            _key(package, field),
            SettingUpsert(value=value, value_type=SettingValueType(value_type)),
        )

    async def clear_override(self, package: str, field: str) -> None:
        await self._service.delete_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, _key(package, field)
        )

    async def list_packages_with_overrides(self) -> list[str]:
        items = await self._service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        pkgs: set[str] = set()
        for item in items:
            if "." not in item.key:
                continue
            pkg, rest = item.key.split(".", 1)
            if "." in rest:
                continue
            pkgs.add(pkg)
        return sorted(pkgs)
