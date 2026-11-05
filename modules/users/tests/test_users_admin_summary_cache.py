"""Admin summaries avoid repeated scans and forget only committed writes."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi_users.password import PasswordHelper
from simple_module_core.invalidation import Invalidation
from simple_module_db.transaction import finalize_session, rollback_session
from sqlalchemy import delete, event, select, update
from users.admin import summary_cache
from users.admin.service import UserService
from users.db_adapter import UserDatabaseWithRoles
from users.manager import UserManager
from users.models import Role, User, UserRole


def service(db, app):
    manager = UserManager(
        UserDatabaseWithRoles(db, User), app.state.users.mailer, app.state.users.settings
    )
    return UserService(db, manager, app)


@pytest.mark.parametrize("method", ["count_user_states", "list_roles"])
async def test_summary_cache_hit_and_expiry(users_app, monkeypatch, method):
    from users.admin import summary_cache

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
async def test_committed_writes_invalidate_summaries(users_app, write):
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
            from datetime import UTC, datetime

            user.invited_at = datetime.now(UTC)
        elif write == "disable":
            await db.execute(update(User).where(User.id == user.id).values(is_active=False))
        elif write == "delete":
            await db.execute(delete(User).where(User.id == user.id))
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
    from users.admin.summary_cache import CHANNEL

    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        before = await svc.count_user_states()
        db.add(User(email="rolledback@example.com", hashed_password="unused"))
        await db.flush()
        await rollback_session(db)
        # A rollback must preserve a warm cache.
        from users.admin import summary_cache

        with patch.object(summary_cache, "load_counts", side_effect=AssertionError("cache miss")):
            assert await svc.count_user_states() == before
        await users_app.state.sm.invalidation.deliver(
            Invalidation(CHANNEL, origin="other-worker").to_wire()
        )
        # Invalidate remotely even when no local write occurred.
        from users.admin import summary_cache

        with (
            patch.object(summary_cache, "load_counts", side_effect=RuntimeError("reloaded")),
            pytest.raises(RuntimeError, match="reloaded"),
        ):
            await svc.count_user_states()


async def test_list_items_use_trusted_construction(users_app, monkeypatch):
    from users.contracts.schemas import UserListItem

    def reject_validation(*args, **kwargs):
        raise AssertionError("DB rows should not be validated again")

    monkeypatch.setattr(UserListItem, "__init__", reject_validation)
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        items, total = await svc.list_users()
        assert total and items[0].model_dump(mode="json")["email"]
        user = await svc.get_with_roles(items[0].id)
        assert svc.to_list_item(user) == items[0]


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_adapter_commits_publish_before_request_finalization(users_app, operation):
    from users.admin.summary_cache import CHANNEL
    from users.contracts.schemas import UserCreate

    messages = []
    users_app.state.sm.invalidation.subscribe(CHANNEL, messages.append)
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        manager = svc._manager
        await svc.count_user_states()
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
        assert messages


async def test_inflight_invalidation_does_not_repopulate_stale_cache(users_app, monkeypatch):
    from users.admin import summary_cache

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
    from users.roles_cache import refresh_roles_cache

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


def _record(app):
    from users.admin.summary_cache import CHANNEL

    messages = []
    app.state.sm.invalidation.subscribe(CHANNEL, messages.append)
    return messages


async def test_uncounted_user_writes_publish_nothing(users_app):
    """Logins, lockout counters and revocations must not chatter on the bus."""
    messages = _record(users_app)
    async with users_app.state.sm.db.session_factory() as db:
        svc = service(db, users_app)
        before = await svc.count_user_states()
        user = (
            await db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one()
        user.session_version = int(user.session_version or 0) + 1
        user.hashed_password = "rotated"
        user.last_login_at = datetime.now(UTC)
        await db.flush()
        await db.execute(
            update(User).where(User.id == user.id).values(failed_login_count=3, session_version=99)
        )
        await finalize_session(db)
        with patch.object(
            summary_cache, "load_counts", side_effect=AssertionError("cache dropped")
        ):
            assert await svc.count_user_states() == before
    assert messages == []


async def test_one_publish_per_transaction(users_app):
    messages = _record(users_app)
    async with users_app.state.sm.db.session_factory() as db:
        db.add(User(email="one@example.com", hashed_password="unused"))
        await db.flush()
        db.add(User(email="two@example.com", hashed_password="unused"))
        await db.flush()
        await db.execute(
            update(User).where(User.email == "one@example.com").values(is_active=False)
        )
        await finalize_session(db)
    assert len(messages) == 1


async def test_savepoint_rollback_keeps_a_later_write_publishing(users_app):
    messages = _record(users_app)
    async with users_app.state.sm.db.session_factory() as db:
        nested = await db.begin_nested()
        db.add(User(email="undone@example.com", hashed_password="unused"))
        await db.flush()
        await nested.rollback()
        db.add(User(email="kept@example.com", hashed_password="unused"))
        await finalize_session(db)
    assert len(messages) == 1
