"""Permissions module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from permissions.constants import _MODULE_AUTH, _MODULE_USERS

if TYPE_CHECKING:
    from fastapi import FastAPI


class PermissionsModule(ModuleBase):
    meta = ModuleMeta(
        name="Permissions",
        route_prefix="/api/permissions",
        view_prefix="/admin/permissions",
        depends_on=[_MODULE_AUTH, _MODULE_USERS],
        i18n_audience="admin",
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from permissions.endpoints.api import router as api
        from permissions.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_permissions(self, registry: PermissionRegistry) -> None:
        from permissions.constants import PERM_MANAGE, PERM_VIEW, PERMISSION_GROUP

        registry.add_group(
            PERMISSION_GROUP,
            [PERM_VIEW, PERM_MANAGE],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"permissions": base}

    async def on_startup(self, app: FastAPI) -> None:
        """Replay persisted role→permission rows into the live registry."""
        from permissions.service import PermissionService

        db_state = app.state.sm.db
        registry = app.state.sm.permissions
        async with db_state.session_factory() as db:
            service = PermissionService(db, registry)
            await service.load_all_into_registry()
            await service.sync_admin_all_permissions()
            await db.commit()
