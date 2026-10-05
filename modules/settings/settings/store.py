"""DB-backed key/value store for module settings (SYSTEM scope).

Wraps the existing SettingService. Keys are namespaced ``<package>.<field>``
to avoid collision with free-form user-defined setting keys.

Reads are deliberately *unmasked*. This store is what applies overrides to the
live settings objects at boot, not what renders them: the masking on the
service's ordinary read path is for the admin screens, and going through it here
would write a row of dots over every real credential the deployment had stored.
The display side masks independently, from the settings object it is given —
see ``_module_settings._field_view``.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from settings.constants import SYSTEM_SCOPE_ID
from settings.contracts.schemas import SettingScope, SettingUpsert, SettingValueType
from settings.models import Setting
from settings.service import SettingService


def _key(package: str, field: str) -> str:
    return f"{package}.{field}"


def package_overrides(
    rows: Iterable[tuple[str, str, str]], package: str
) -> dict[str, tuple[str, str]]:
    """Map ``(key, value, value_type)`` rows to ``{field_name: (raw, value_type)}``.

    The one place the ``<package>.<field>`` key format is interpreted, shared by
    the async :meth:`SettingsStore.get_overrides` and the sync
    :func:`get_overrides_sync` so the two cannot drift.
    """
    prefix = f"{package}."
    out: dict[str, tuple[str, str]] = {}
    for key, value, value_type in rows:
        if not key.startswith(prefix):
            continue
        field_name = key[len(prefix) :]
        if "." in field_name:
            continue
        out[field_name] = (value, value_type)
    return out


def get_overrides_sync(session: Session, package: str) -> dict[str, tuple[str, str]]:
    """Sync twin of :meth:`SettingsStore.get_overrides` for worker processes.

    Reads SYSTEM-scope rows through a plain sync ``Session`` (unmasked, like the
    async path — this feeds live settings objects, not a screen).
    """
    stmt = select(Setting.key, Setting.value, Setting.value_type).where(
        Setting.scope == SettingScope.SYSTEM.value,
        Setting.scope_id == SYSTEM_SCOPE_ID,
        Setting.key.startswith(f"{package}.", autoescape=True),
    )
    return package_overrides(((k, v, t) for k, v, t in session.execute(stmt)), package)


class SettingsStore:
    """SYSTEM-scoped key/value store keyed by ``(package, field)``."""

    def __init__(self, service: SettingService) -> None:
        self._service = service

    async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]:
        """Return ``{field_name: (raw_value, value_type)}`` for a package."""
        items = await self._service.list_by_scope_unmasked(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        return package_overrides(((i.key, i.value, i.value_type) for i in items), package)

    async def all_override_fields(self) -> dict[str, frozenset[str]]:
        """Return ``{package: {field_name, ...}}`` for every stored override.

        One query for the whole screen. ``get_overrides`` re-reads the entire
        SYSTEM scope per package, so calling it in a loop over the installed
        modules is one full read per module for the same rows.
        """
        items = await self._service.list_by_scope_unmasked(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
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
        items = await self._service.list_by_scope_unmasked(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        pkgs: set[str] = set()
        for item in items:
            if "." not in item.key:
                continue
            pkg, rest = item.key.split(".", 1)
            if "." in rest:
                continue
            pkgs.add(pkg)
        return sorted(pkgs)
