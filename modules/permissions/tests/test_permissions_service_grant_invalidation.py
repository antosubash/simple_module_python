"""Service callers get durable direct-grant invalidation too (#687, #621)."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from permissions.grants import CHANNEL, clear_grants_cache, direct_grant_source, subscribe
from permissions.models import UserPermission
from permissions.service import PermissionService
from simple_module_core.invalidation import InvalidationBus
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.requests import Request


@pytest.mark.parametrize("with_app", [False, True])
@pytest.mark.parametrize("commit", [False, True])
@pytest.mark.parametrize("clear", [False, True])
async def test_service_invalidates_user_grants_only_on_commit(db_session, commit, clear, with_app):
    user = DirectoryUser(id=str(uuid.uuid4()), email="target@test", roles=())

    class Directory(NullUserDirectory):
        async def get_many(self, db, ids, *, with_roles=False):
            return {user.id: user} if user.id in ids else {}

    registry = PermissionRegistry()
    registry.add_group("Test", ["test.view"])
    bus = InvalidationBus()
    subscribe(bus)
    messages = []
    bus.subscribe(CHANNEL, messages.append)
    app = FastAPI()
    app.state.sm = SimpleNamespace(
        invalidation=bus, db=SimpleNamespace(session_factory=async_sessionmaker(db_session.bind))
    )
    request = Request({"type": "http", "app": app})
    user_id = uuid.UUID(user.id)
    if clear:
        db_session.add(UserPermission(user_id=user_id, permission_key="test.view"))
        await db_session.commit()
    clear_grants_cache()
    before = frozenset({"test.view"} if clear else set())
    after = frozenset() if clear else frozenset({"test.view"})
    try:
        assert await direct_grant_source(request, user) == before
        service = PermissionService(
            db_session, registry, Directory(), app=app if with_app else None
        )
        await service.set_user_permissions(user_id, [] if clear else ["test.view"])
        assert await direct_grant_source(request, user) == before
        assert messages == []
        if commit:
            await finalize_session(db_session)
        else:
            await rollback_session(db_session)
        assert len(messages) == int(commit and with_app)
        assert await direct_grant_source(request, user) == (after if commit else before)
    finally:
        clear_grants_cache()
