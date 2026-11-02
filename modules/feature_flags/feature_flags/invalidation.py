"""Re-read flag overrides after commit or a remote invalidation."""

from fastapi import FastAPI
from simple_module_core.invalidation import Invalidation, InvalidationBus
from simple_module_core.invalidation_refresh import InvalidationRefresh
from simple_module_core.tenant_events import TENANT_DELETED_CHANNEL

from feature_flags.service import FeatureFlagService

CHANNEL = "feature_flags.overrides"


def subscribe(bus: InvalidationBus, app: FastAPI) -> InvalidationRefresh:
    def forget_tenant(message: Invalidation) -> None:
        if message.key is not None:
            app.state.sm.feature_flags.clear_tenant_overrides(message.key)

    bus.subscribe(TENANT_DELETED_CHANNEL, forget_tenant)

    async def reload(_key: str | None) -> None:
        async with app.state.sm.db.session_factory() as db:
            await FeatureFlagService(db).hydrate_registry(app.state.sm.feature_flags)

    return InvalidationRefresh(bus, CHANNEL, reload)
