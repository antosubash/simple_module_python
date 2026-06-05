"""Services dataclass — framework-scoped singleton container."""

from __future__ import annotations

import pytest
from simple_module_core.services import Services


class TestServices:
    async def test_services_is_frozen(self) -> None:
        """Mutation after construction must raise — singletons don't change at runtime."""
        s = _make_services()
        with pytest.raises((AttributeError, TypeError)):
            s.settings = None  # type: ignore[misc,assignment]  # ty: ignore[invalid-assignment]

    async def test_services_has_slots(self) -> None:
        """Slotted dataclass prevents silent attribute additions (the original bloat pattern)."""
        s = _make_services()
        with pytest.raises((AttributeError, TypeError)):
            s.rogue_new_attribute = 42  # type: ignore[attr-defined]  # ty: ignore[invalid-assignment]

    async def test_services_round_trip_field_access(self) -> None:
        """Every declared field must be readable after construction."""
        s = _make_services()
        assert s.settings is _SENTINEL_SETTINGS
        assert s.db is _SENTINEL_DB
        assert s.event_bus is _SENTINEL_EVENT_BUS
        assert s.menu_registry is _SENTINEL_MENU
        assert s.permissions is _SENTINEL_PERMS
        assert s.feature_flags is _SENTINEL_FLAGS
        assert s.health_registry is _SENTINEL_HEALTH
        assert s.public_routes is _SENTINEL_PUBLIC_ROUTES
        assert s.i18n_registry is _SENTINEL_I18N
        assert s.inertia_config is _SENTINEL_INERTIA
        assert s.modules == ()


_SENTINEL_SETTINGS = object()
_SENTINEL_DB = object()
_SENTINEL_EVENT_BUS = object()
_SENTINEL_MENU = object()
_SENTINEL_PERMS = object()
_SENTINEL_FLAGS = object()
_SENTINEL_HEALTH = object()
_SENTINEL_PUBLIC_ROUTES = object()
_SENTINEL_I18N = object()
_SENTINEL_INERTIA = object()


def _make_services() -> Services:
    """Construct a Services instance with sentinel values for structural tests."""
    return Services(
        settings=_SENTINEL_SETTINGS,  # type: ignore[arg-type]
        db=_SENTINEL_DB,  # type: ignore[arg-type]
        event_bus=_SENTINEL_EVENT_BUS,  # type: ignore[arg-type]
        menu_registry=_SENTINEL_MENU,  # type: ignore[arg-type]
        permissions=_SENTINEL_PERMS,  # type: ignore[arg-type]
        feature_flags=_SENTINEL_FLAGS,  # type: ignore[arg-type]
        health_registry=_SENTINEL_HEALTH,  # type: ignore[arg-type]
        public_routes=_SENTINEL_PUBLIC_ROUTES,  # type: ignore[arg-type]
        i18n_registry=_SENTINEL_I18N,  # type: ignore[arg-type]
        inertia_config=_SENTINEL_INERTIA,  # type: ignore[arg-type]
        modules=(),
    )
