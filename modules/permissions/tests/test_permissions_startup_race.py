"""Independent workers can synchronize newly registered admin grants (#732)."""

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from permissions.models import Base, RolePermission
from permissions.module import PermissionsModule
from permissions.service import PermissionService
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.listeners import register_listeners
from simple_module_db.session import init_db
from sqlalchemy import select


async def test_permissions_concurrent_module_startup(tmp_path, monkeypatch):
    state = init_db(f"sqlite+aiosqlite:///{tmp_path}/startup.db")
    register_listeners(state)
    try:
        async with state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        apps = []
        for _ in range(2):
            app = FastAPI()
            registry = PermissionRegistry()
            registry.add("test.view")
            app.state.sm = SimpleNamespace(db=state, permissions=registry)
            apps.append(app)
        barrier = asyncio.Barrier(2)
        original = PermissionService._get_role_keys

        async def synchronized_read(self, name):
            keys = await original(self, name)
            assert keys == []
            await asyncio.wait_for(barrier.wait(), 5)
            return keys

        with monkeypatch.context() as patch:
            patch.setattr(PermissionService, "_get_role_keys", synchronized_read)
            results = await asyncio.gather(
                *(PermissionsModule().on_startup(app) for app in apps), return_exceptions=True
            )
        assert results == [None, None]
        await PermissionsModule().on_startup(apps[0])
        async with state.session_factory() as db:
            rows = (await db.execute(select(RolePermission))).scalars().all()
            assert [(row.role_name, row.permission_key) for row in rows] == [("admin", "test.view")]
    finally:
        await state.engine.dispose()
