"""Tests for UserService domain-level error behavior."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


def _build_service(session, users_app):
    """Build a UserService directly (bypass FastAPI Depends)."""
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    user_db = UserDatabaseWithRoles(session, User)
    manager = UserManager(
        user_db,
        users_app.state.users.mailer,
        users_app.state.users.settings,
    )
    return UserService(session, manager)


@pytest.mark.anyio
async def test_disable_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.disable(uuid.uuid4())


@pytest.mark.anyio
async def test_enable_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.enable(uuid.uuid4())


@pytest.mark.anyio
async def test_set_roles_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.set_roles(uuid.uuid4(), ["user"])


@pytest.mark.anyio
async def test_generate_reset_link_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.generate_reset_link(uuid.uuid4(), "http://testserver")


@pytest.mark.anyio
async def test_get_list_item_unknown_user_raises_user_not_found(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        service = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await service.get_list_item(uuid.uuid4())


@pytest.mark.anyio
async def test_to_list_item_includes_created_at(users_app):
    """`UserListItem` carries `created_at` sourced from AuditMixin."""
    from fastapi_users.password import PasswordHelper

    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="ts@example.com",
            hashed_password=PasswordHelper().hash("x"),
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        svc = UserService(session, manager)
        item = await svc.get_list_item(user.id)
        assert item.created_at is not None


# ---------------------------------------------------------------------------
# Filter + sort tests (Task 2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_users_status_disabled_filter(users_app):
    """list_users(status='disabled') returns only disabled users."""
    from fastapi_users.password import PasswordHelper

    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        pw = PasswordHelper().hash("x")
        active_user = __import__("users.models", fromlist=["User"]).User(
            id=uuid.uuid4(),
            email="active@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        disabled_user = __import__("users.models", fromlist=["User"]).User(
            id=uuid.uuid4(),
            email="disabled@example.com",
            hashed_password=pw,
            is_active=False,
            is_superuser=False,
            is_verified=True,
            disabled_at=datetime.now(UTC),
        )
        session.add(active_user)
        session.add(disabled_user)
        await session.flush()

        svc = _build_service(session, users_app)
        items, total = await svc.list_users(status="disabled")

    assert total == 1
    assert items[0].email == "disabled@example.com"


@pytest.mark.anyio
async def test_list_users_role_filter(users_app):
    """list_users(role_name='admin') returns only users with that role."""
    from fastapi_users.password import PasswordHelper

    from users.constants import ADMIN_ROLE_ID
    from users.models import User, UserRole
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        pw = PasswordHelper().hash("x")
        admin_user = User(
            id=uuid.uuid4(),
            email="role_admin@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        plain_user = User(
            id=uuid.uuid4(),
            email="role_plain@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(admin_user)
        session.add(plain_user)
        await session.flush()

        session.add(UserRole(user_id=admin_user.id, role_id=ADMIN_ROLE_ID))
        await session.flush()

        svc = _build_service(session, users_app)
        items, total = await svc.list_users(role_name="admin")

    assert total == 1
    assert items[0].email == "role_admin@example.com"


@pytest.mark.anyio
async def test_list_users_verified_filter(users_app):
    """list_users(verified='no') returns only unverified users."""
    from fastapi_users.password import PasswordHelper

    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        pw = PasswordHelper().hash("x")
        verified_user = User(
            id=uuid.uuid4(),
            email="verified@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        unverified_user = User(
            id=uuid.uuid4(),
            email="unverified@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(verified_user)
        session.add(unverified_user)
        await session.flush()

        svc = _build_service(session, users_app)
        items, total = await svc.list_users(verified="no")

    assert total == 1
    assert items[0].email == "unverified@example.com"


@pytest.mark.anyio
async def test_list_users_sort_last_login_desc_nulls_last(users_app):
    """list_users(sort='last_login_at', order='desc') orders recent→old→never (NULLs last)."""
    from fastapi_users.password import PasswordHelper

    from users.models import User
    from users.service import UserService

    recent_ts = datetime(2024, 6, 1, tzinfo=UTC)
    old_ts = datetime(2023, 1, 1, tzinfo=UTC)

    async with users_app.state.sm.db.session_factory() as session:
        pw = PasswordHelper().hash("x")
        user_recent = User(
            id=uuid.uuid4(),
            email="recent@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
            last_login_at=recent_ts,
        )
        user_old = User(
            id=uuid.uuid4(),
            email="old@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
            last_login_at=old_ts,
        )
        user_never = User(
            id=uuid.uuid4(),
            email="never@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
            last_login_at=None,
        )
        session.add(user_recent)
        session.add(user_old)
        session.add(user_never)
        await session.flush()

        svc = _build_service(session, users_app)
        items, total = await svc.list_users(sort="last_login_at", order="desc")

    assert total == 3
    emails = [i.email for i in items]
    assert emails == ["recent@example.com", "old@example.com", "never@example.com"]
