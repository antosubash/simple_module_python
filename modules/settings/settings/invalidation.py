"""Rehydrate module settings and notify local consumers only after durable writes."""

from fastapi import FastAPI
from simple_module_core.app_state import get_services
from simple_module_core.events import EventBus
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.invalidation_refresh import InvalidationRefresh
from simple_module_core.module_settings import module_settings_registry
from simple_module_core.settings_hydrate import hydrate_settings

from settings.contracts.events import SettingsReloaded
from settings.store import SettingsStore

CHANNEL = "settings.modules"


async def reload_package(app: FastAPI, bus: EventBus, store: SettingsStore, package: str) -> None:
    cls = module_settings_registry(app).get(package)
    if cls is None:
        return
    services = getattr(app.state, package)
    hydrated = await hydrate_settings(cls, store, package, lenient=True)
    changed = tuple(
        sorted(
            name
            for name in cls.model_fields
            if getattr(services.settings, name) != getattr(hydrated, name)
        )
    )
    services.settings = hydrated
    if changed:
        await bus.publish(SettingsReloaded(package=package, changed=changed))


def reload_on_commit(app: FastAPI, bus: EventBus, store: SettingsStore, package: str) -> None:
    async def committed() -> None:
        invalidation = getattr(get_services(app), "invalidation", None)
        if invalidation is None:
            await reload_package(app, bus, store, package)
        else:
            await invalidation.publish(CHANNEL, key=package)

    store.on_commit(committed)


def subscribe(bus: InvalidationBus, app: FastAPI) -> InvalidationRefresh:
    from settings.service import SettingService

    async def reload(key: str | None) -> None:
        async with app.state.sm.db.session_factory() as db:
            store = SettingsStore(SettingService(db))
            packages = [key] if key is not None else module_settings_registry(app).all_packages()
            for package in packages:
                await reload_package(app, app.state.sm.event_bus, store, package)

    return InvalidationRefresh(bus, CHANNEL, reload)
