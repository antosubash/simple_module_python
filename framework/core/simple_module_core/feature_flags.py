"""Feature flag registry — modules declare toggleable features."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlagDefinition:
    """A feature that can be toggled on/off at runtime."""

    name: str
    description: str = ""
    default_enabled: bool = False


class FeatureFlagRegistry:
    """Central registry of all feature flags."""

    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlagDefinition] = {}
        self._overrides: dict[str, bool] = {}

    def add(self, flag: FeatureFlagDefinition) -> None:
        self._flags[flag.name] = flag

    def is_enabled(self, name: str) -> bool:
        if name in self._overrides:
            return self._overrides[name]
        flag = self._flags.get(name)
        return flag.default_enabled if flag else False

    def set_override(self, name: str, enabled: bool) -> None:
        self._overrides[name] = enabled

    def clear_override(self, name: str) -> None:
        self._overrides.pop(name, None)

    @property
    def all_flags(self) -> list[FeatureFlagDefinition]:
        return list(self._flags.values())
