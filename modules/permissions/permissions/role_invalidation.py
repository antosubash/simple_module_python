"""Reload committed role grants in every worker, preserving code-registered mappings."""

from fastapi import FastAPI
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.invalidation_refresh import InvalidationRefresh

from permissions.service import PermissionService

CHANNEL = "permissions.role_grants"


def subscribe(bus: InvalidationBus, app: FastAPI) -> InvalidationRefresh:
    async def reload(_key: str | None) -> None:
        async with app.state.sm.db.session_factory() as db:
            await PermissionService(db, app.state.sm.permissions).load_all_into_registry()

    return InvalidationRefresh(bus, CHANNEL, reload)
