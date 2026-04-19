"""FastAPI dependencies for the Settings module.

Consumers in other modules should almost always depend on ``SettingsDep``
(the accessor) rather than ``SettingService`` directly — the accessor is
bound to the current request's user/tenant so ``get_bool(key)`` etc. just
work.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from settings.constants import MODULE_PACKAGE
from settings.contracts.accessor import SettingsAccessor
from settings.contracts.registry import SettingsRegistry
from settings.service import SettingService


async def get_setting_service(
    db: AsyncSession = Depends(get_db),
) -> SettingService:
    return SettingService(db)


def get_settings_registry(request: Request) -> SettingsRegistry:
    """Return the app-wide settings registry populated during boot."""
    services = getattr(request.app.state, MODULE_PACKAGE)
    return services.registry


async def get_settings_accessor(
    request: Request,
    service: SettingService = Depends(get_setting_service),
    registry: SettingsRegistry = Depends(get_settings_registry),
) -> SettingsAccessor:
    """Build a request-scoped accessor bound to the caller's user/tenant.

    ``request.state.user`` is populated by ``users.middleware`` (carries a
    ``UserContext``). ``request.state.tenant_id`` is populated by
    ``TenantMiddleware`` when ``multi_tenant=True``. Both are optional —
    the accessor gracefully degrades to lower scopes (or the registered
    default) if the request is unauthenticated or untenanted.
    """
    user = getattr(request.state, "user", None)
    user_id = str(user.id) if user is not None else None
    tenant_id = getattr(request.state, "tenant_id", None)
    return SettingsAccessor(service, registry, user_id=user_id, tenant_id=tenant_id)


# Convenience aliases for typing annotations in consumer modules.
SettingServiceDep = Annotated[SettingService, Depends(get_setting_service)]
SettingsDep = Annotated[SettingsAccessor, Depends(get_settings_accessor)]
