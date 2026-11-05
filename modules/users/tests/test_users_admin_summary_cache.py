"""Admin summaries avoid repeated scans, forget committed writes and publish explicitly."""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi_users.password import PasswordHelper
from simple_module_core.invalidation import Invalidation
from simple_module_db.callbacks import register_on_commit
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy import event, select
from users.admin import summary_cache
from users.admin.service import UserService
from users.contracts.schemas import UserCreate, UserListItem
from users.db_adapter import UserDatabaseWithRoles
from users.manager import UserManager
from users.models import Role, User, UserRole
from users.roles_cache import refresh_roles_cache


def service(db, app):
    manager = UserManager(
        UserDatabaseWithRoles(db, User), app.state.users.mailer, app.state.users.settings
    )
    return UserService(db, manager, app)


def _record(app):
    messages = []
    app.state.sm.invalidation.subscribe(summary_cache.CHANNEL, messages.append)
    return messages


async def _make_user(app, email="target@example.com", **fields) -> uuid.UUID:
    async with app.state.sm.db.session_factory() as db:
        user = User(email=email, hashed_password=PasswordHelper().hash("SecurePass1!"), **fields)
        db.add(user)
        await finalize_session(db)
        return user.id


@pytest.mark.parametrize("method", ["count_user_states", "list_roles"])
async def test_summary_cache_hit_and_expiry(users_app, monkeypatch, method):
    queries = []
    event.listen(
        users_app.state.sm.db.engine.sync_engine,
        "before_cursor_execute",
        lambda *args: queries.append(args[2]),
    )
    async with users_app.state.sm.db.session_factory() as db:
        get = getattr(service(db, users_app), method)
        first = await get()
        queries.clear()
        assert await get() == first
        assert queries == []
        # Values handed to callers must not let them corrupt the cached result.
        first.clear()
        assert await get()
        monkeypatch.setattr(summary_cache.time, "monotonic", lambda: 10**12)
        await get()
        assert queries


@pytest.mark.parametrize(
    "write", ["create", "verify", "invite", "disable", "delete", "role", "membership"]
)
async def test_local_orm_writes_clear_this_workers_cache_on_commit(users_app, write):
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        user = User(
            email="cached@example.com", hashed_password=PasswordHelper().hash("SecurePass1!")
        )
        db.add(user)
        await finalize_session(db)
        before = await svc.count_user_states()
        roles_before = await svc.list_roles()
        if write == "create":
            db.add(User(email="added@example.com", hashed_password="unused"))
        elif write == "verify":
            user.is_verified = True
        elif write == "invite":
            user.invited_at = datetime.now(UTC)
        elif write == "disable":
            user.is_active = False
        elif write == "delete":
            await db.delete(user)
        elif write == "role":
            db.add(Role(name="reviewer"))
        else:
            role = (await db.execute(select(Role).where(Role.name == "user"))).scalar_one()
            db.add(UserRole(user_id=user.id, role_id=role.id))
        await finalize_session(db)
        if write in ("role", "membership"):
            assert await svc.list_roles() != roles_before
        else:
            assert await svc.count_user_states() != before


async def test_rollback_and_remote_invalidation(users_app):
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        before = await svc.count_user_states()
        db.add(User(email="rolledback@example.com", hashed_password="unused"))
        await db.flush()
        await rollback_session(db)
        # A rollback must preserve a warm cache.
        with patch.object(summary_cache, "load_counts", side_effect=AssertionError("cache miss")):
            assert await svc.count_user_states() == before
        await users_app.state.sm.invalidation.deliver(
            Invalidation(summary_cache.CHANNEL, origin="other-worker").to_wire()
        )
        # Invalidate remotely even when no local write occurred.
        with (
            patch.object(summary_cache, "load_counts", side_effect=RuntimeError("reloaded")),
            pytest.raises(RuntimeError, match="reloaded"),
        ):
            await svc.count_user_states()


async def _call(svc, method, user_id):
    if method == "create_user":
        await svc.create_user("new@example.com", "SecurePass1!", None, ["user"], created_by=None)
    elif method == "invite":
        await svc.invite("invited@example.com", None, ["user"])
    elif method == "set_roles":
        await svc.set_roles(user_id, [])
    else:
        await getattr(svc, method)(user_id)


_WRITES = ["create_user", "invite", "delete_user", "disable", "enable", "mark_verified"]


@pytest.mark.parametrize("method", [*_WRITES, "set_roles"])
async def test_admin_writes_publish_once_after_commit(users_app, method):
    user_id = await _make_user(users_app, is_active=method != "enable")
    messages = _record(users_app)
    async with users_app.state.sm.db.session_factory() as db:
        await _call(service(db, users_app), method, user_id)
        assert messages == []
        await finalize_session(db)
    assert len(messages) == 1


@pytest.mark.parametrize("method", [*_WRITES, "set_roles"])
async def test_admin_writes_publish_nothing_on_rollback(users_app, method):
    user_id = await _make_user(users_app, is_active=method != "enable")
    messages = _record(users_app)
    async with users_app.state.sm.db.session_factory() as db:
        await _call(service(db, users_app), method, user_id)
        await rollback_session(db)
    assert messages == []


async def test_login_and_lockout_writes_publish_nothing(users_app, anon_client):
    messages = _record(users_app)
    for _ in range(3):
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "wrong-password"},
        )
        assert resp.status_code == 400, resp.text
    resp = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1!"},
    )
    assert resp.status_code == 204, resp.text
    assert messages == []


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_adapter_commits_run_queued_on_commit_callbacks(users_app, operation):
    ran = []
    async with users_app.state.sm.db.session_factory() as db:
        manager = service(db, users_app)._manager
        register_on_commit(db, lambda: ran.append(operation))
        if operation == "create":
            await manager.create(
                UserCreate(email="adapter@example.com", password="SecurePass1!", is_verified=True)
            )
        else:
            user = await manager.get_by_email("admin@example.com")
            if operation == "update":
                await manager._update(user, {"is_active": False})
            else:
                await manager.delete(user)
        assert ran == [operation]


async def test_list_items_use_trusted_construction(users_app, monkeypatch):
    def reject_validation(*args, **kwargs):
        raise AssertionError("DB rows should not be validated again")

    monkeypatch.setattr(UserListItem, "__init__", reject_validation)
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        items, total = await svc.list_users()
        assert total and items[0].model_dump(mode="json")["email"]
        user = await svc.get_with_roles(items[0].id)
        assert svc.to_list_item(user) == items[0]


async def test_inflight_invalidation_does_not_repopulate_stale_cache(users_app, monkeypatch):
    calls = 0

    async def racing_load(db):
        nonlocal calls
        calls += 1
        if calls == 1:
            await users_app.state.sm.invalidation.publish(summary_cache.CHANNEL)
        return {"active": calls, "invited": 0, "unverified": 0}

    monkeypatch.setattr(summary_cache, "load_counts", racing_load)
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        assert (await svc.count_user_states())["active"] == 1
        assert (await svc.count_user_states())["active"] == 2
        assert (await svc.count_user_states())["active"] == 2


async def test_role_options_do_not_hydrate_orm_rows(users_app):
    loaded = []

    def record(*args):
        loaded.append(args[0])

    event.listen(Role, "load", record)
    try:
        async with users_app.state.sm.db.session_factory() as db:
            assert await service(db, users_app).list_roles()
            assert await refresh_roles_cache(users_app)
        assert loaded == []
    finally:
        event.remove(Role, "load", record)
