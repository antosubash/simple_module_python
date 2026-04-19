"""Feature flag registry — modules declare toggleable features.

Overrides live at two scopes:

* **system** — applies to every request unless a tenant override exists
* **tenant** — applies only when ``is_enabled`` is called with a matching
  ``tenant_id``; a per-tenant value beats the system override

Resolution order: tenant override > system override > definition default.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlagDefinition:
    """A feature that can be toggled on/off at runtime."""

    name: str
    description: str = ""
    default_enabled: bool = False


class FeatureFlagRegistry:
    """In-memory registry of flag definitions and their resolved overrides."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlagDefinition] = {}
        self._system_overrides: dict[str, bool] = {}
        self._tenant_overrides: dict[tuple[str, str], bool] = {}

    def add(self, flag: FeatureFlagDefinition) -> None:
        self._flags[flag.name] = flag

    def is_enabled(self, name: str, tenant_id: str | None = None) -> bool:
        if tenant_id is not None:
            tenant_value = self._tenant_overrides.get((name, tenant_id))
            if tenant_value is not None:
                return tenant_value
        if name in self._system_overrides:
            return self._system_overrides[name]
        flag = self._flags.get(name)
        return flag.default_enabled if flag else False

    def set_override(self, name: str, enabled: bool, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._system_overrides[name] = enabled
        else:
            self._tenant_overrides[(name, tenant_id)] = enabled

    def clear_override(self, name: str, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._system_overrides.pop(name, None)
        else:
            self._tenant_overrides.pop((name, tenant_id), None)

    def tenant_override(self, name: str, tenant_id: str) -> bool | None:
        """Return the per-tenant override for ``(name, tenant_id)`` if set, else None."""
        return self._tenant_overrides.get((name, tenant_id))

    def system_override(self, name: str) -> bool | None:
        """Return the system-level override for ``name`` if set, else None."""
        return self._system_overrides.get(name)

    @property
    def all_flags(self) -> list[FeatureFlagDefinition]:
        return list(self._flags.values())
