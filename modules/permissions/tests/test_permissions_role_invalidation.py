"""Role overlays follow durable DB changes, including another worker's revocation."""

import uuid

import pytest
from permissions.models import RolePermission
from permissions.service import PermissionService
from simple_module_core.invalidation import Invalidation
from simple_module_core.permissions import PermissionRegistry
from simple_module_db.transaction import finalize_session, rollback_session
from users.models import Role


@pytest.mark.parametrize("commit", [False, True])
@pytest.mark.parametrize("clear", [False, True])
async def test_role_overlay_waits_for_commit(db_session, commit, clear):
    role = Role(id=uuid.uuid4(), name="editor")
    db_session.add(role)
    await db_session.flush()
    registry = PermissionRegistry()
    registry.add_group("Test", ["test.view"])
    role_id = role.id
    if clear:
        db_session.add(RolePermission(role_name="editor", permission_key="test.view"))
        await db_session.commit()
        registry.set_role_overlay("editor", ["test.view"])
    service = PermissionService(db_session, registry)
    await service.set_role_permissions(role_id, [] if clear else ["test.view"])
    assert ("test.view" in registry.role_map.get("editor", [])) is clear
    if commit:
        await finalize_session(db_session)
    else:
        await rollback_session(db_session)
    assert ("test.view" in registry.role_map.get("editor", [])) is (clear != commit)


async def test_remote_role_change_and_removal_reload_overlay(app):
    registry = app.state.sm.permissions
    registry.map_role("editor", ["code.grant"])
    factory = app.state.sm.db.session_factory
    async with factory() as db:
        row = RolePermission(role_name="editor", permission_key="db.grant")
        db.add(row)
        await db.commit()
    bus = app.state.sm.invalidation
    message = Invalidation(channel="permissions.role_grants", key="editor", origin="other")
    await bus.deliver(message.to_wire())
    assert set(registry.role_map["editor"]) == {"code.grant", "db.grant"}
    async with factory() as db:
        await db.delete(await db.get(RolePermission, ("editor", "db.grant")))
        await db.commit()
    await bus.deliver(message.to_wire())
    assert registry.role_map["editor"] == ["code.grant"]


@pytest.mark.parametrize("commit", [False, True])
async def test_role_request_publishes_only_after_commit(app, commit):
    from permissions.deps import get_permission_service
    from starlette.requests import Request

    registry = app.state.sm.permissions
    registry.add_group("Test", ["test.view"])
    messages = []
    app.state.sm.invalidation.subscribe("permissions.role_grants", messages.append)
    async with app.state.sm.db.session_factory() as db:
        role = Role(id=uuid.uuid4(), name="editor")
        db.add(role)
        await db.flush()
        from auth.contracts.schemas import UserContext

        request = Request({"type": "http", "app": app})
        request.state.user = UserContext(
            id="admin", email="admin@test", name="Admin", roles=["admin"]
        )
        service = await get_permission_service(request, db, registry)
        await service.set_role_permissions(role.id, ["test.view"])
        assert "test.view" not in registry.role_map.get("editor", [])
        assert messages == []
        if commit:
            await finalize_session(db)
        else:
            await rollback_session(db)
    assert ("test.view" in registry.role_map.get("editor", [])) is commit
    assert len(messages) == int(commit)
