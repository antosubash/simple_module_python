"""A direct grant in one application cannot authorize another (#736)."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from permissions.grants.source import CHANNEL, direct_grant_source, subscribe
from permissions.models import Base, UserPermission
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.session import init_db
from simple_module_hosting.permissions import RequiresPermission
from sqlalchemy import delete
from starlette.requests import Request


@pytest.mark.parametrize("all_users", [False, True])
async def test_permissions_grants_and_invalidations_are_app_scoped(all_users):
    user_id = uuid.uuid4()
    states = [init_db("sqlite+aiosqlite:///:memory:") for _ in range(2)]
    apps, requests = [], []
    try:
        for state in states:
            async with state.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            registry = PermissionRegistry()
            registry.add("settings.edit")
            registry.add_grant_source(direct_grant_source)
            app = FastAPI()
            app.state.sm = SimpleNamespace(
                db=state, permissions=registry, invalidation=InvalidationBus()
            )
            apps.append(app)
            requests.append(
                Request(
                    {
                        "type": "http",
                        "app": app,
                        "method": "PUT",
                        "path": "/",
                        "headers": [],
                        "state": {"user": SimpleNamespace(id=str(user_id), roles=[])},
                    }
                )
            )
        async with states[0].session_factory() as db:
            db.add(UserPermission(user_id=user_id, permission_key="settings.edit"))
            await db.commit()

        async def gate(request):
            scope = {**request.scope, "state": {"user": request.state.user}}
            await RequiresPermission("settings.edit")(Request(scope))

        with pytest.raises(HTTPException) as denied:
            await gate(requests[1])
        assert denied.value.status_code == 403
        await gate(requests[0])
        with pytest.raises(HTTPException) as denied:
            await gate(requests[1])
        assert denied.value.status_code == 403
        # Only app A's bus may evict app A's warmed grant.
        for app in apps:
            subscribe(app.state.sm.invalidation, app)
        async with states[0].session_factory() as db:
            await db.execute(delete(UserPermission))
            await db.commit()
        await apps[1].state.sm.invalidation.publish(
            CHANNEL, key=None if all_users else str(user_id)
        )
        await gate(requests[0])
        await apps[0].state.sm.invalidation.publish(
            CHANNEL, key=None if all_users else str(user_id)
        )
        with pytest.raises(HTTPException) as denied:
            await gate(requests[0])
        assert denied.value.status_code == 403
    finally:
        for state in states:
            await state.engine.dispose()
