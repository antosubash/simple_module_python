"""Registry of per-module pydantic BaseSettings classes.

Populated during each module's ``register_settings`` via
``register_module_settings``. The hosting lifespan reads this at startup
to hydrate every module's effective settings from the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_settings import BaseSettings


@dataclass(slots=True)
class ModuleSettingsRegistry:
    """In-memory map of ``package`` → ``BaseSettings`` subclass."""

    _classes: dict[str, type[BaseSettings]] = field(default_factory=dict)

    def register(self, package: str, cls: type[BaseSettings]) -> None:
        if package in self._classes:
            raise ValueError(f"{package!r} already registered")
        self._classes[package] = cls

    def get(self, package: str) -> type[BaseSettings] | None:
        return self._classes.get(package)

    def all_packages(self) -> list[str]:
        return sorted(self._classes)

    def items(self) -> list[tuple[str, type[BaseSettings]]]:
        return sorted(self._classes.items())
