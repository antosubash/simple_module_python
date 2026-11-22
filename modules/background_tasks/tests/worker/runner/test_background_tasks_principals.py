"""The worker's real async session factory can build principals without an app."""

import uuid

from background_tasks.core import sync_db
from background_tasks.outbox import worker
from background_tasks.worker import principals
from simple_module_core.access.principals import PRINCIPALS_KEY
from simple_module_db.principals import principal_for
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


async def test_worker_principal_without_app(settings, tmp_path, monkeypatch):
    from fastapi import FastAPI
    from permissions.models import RolePermission, UserPermission
    from tenants.models import Membership, Tenant
    from users.models import Role, User, UserRole

    path = tmp_path / "principals.db"
    engine = create_engine(f"sqlite:///{path}")
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    try:
        for model in (User, Tenant, UserPermission):
            model.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(User(id=user_id, email="worker@example.com", hashed_password="x"))
            db.add(Role(id=role_id, name="reader"))
            db.add(Tenant(id="own", name="Worker tenant", slug="worker"))
            db.flush()
            db.add(UserRole(user_id=user_id, role_id=role_id))
            db.add(Membership(user_id=str(user_id), tenant_id="own", role="member"))
            db.add(RolePermission(role_name="reader", permission_key="test.role"))
            db.add(UserPermission(user_id=user_id, permission_key="test.direct"))
            db.commit()
    finally:
        engine.dispose()

    settings.modules_enabled = ["Auth", "Users", "Tenants", "Permissions"]
    settings.database_url = f"sqlite+aiosqlite:///{path}"
    for name in ("_host_settings", "_app_registry", "_revision"):
        monkeypatch.setattr(principals, name, getattr(principals, name))
    principals.configure_principals(settings)

    def no_app(*args, **kwargs):
        raise AssertionError("Workers must not construct a FastAPI app")

    monkeypatch.setattr(FastAPI, "__init__", no_app)
    monkeypatch.setattr(sync_db, "async_database_url", lambda: settings.database_url)
    cache = {}
    monkeypatch.setattr(worker, "worker_loop_cache", lambda: cache)
    factory = worker.worker_session_factory()
    registry = factory.kw["info"][PRINCIPALS_KEY]
    registry.permissions.map_role("tenant:member", ["test.member"])
    try:
        async with factory() as db:
            who = await principal_for(db, str(user_id), "own")
            assert who.permissions == {
                "test.role",
                "test.direct",
                "test.member",
                "tenants.members.view",
            }
            assert await principal_for(db, str(user_id), "other") is None
            with Session(engine) as sync:
                grant = sync.get(UserPermission, (user_id, "test.direct"))
                sync.delete(grant)
                role = sync.get(RolePermission, ("reader", "test.role"))
                sync.delete(role)
                sync.commit()
        async with factory() as db:
            who = await principal_for(db, str(user_id), "own")
            assert "test.role" not in who.permissions
            assert "test.direct" not in who.permissions
    finally:
        await factory.kw["bind"].dispose()
