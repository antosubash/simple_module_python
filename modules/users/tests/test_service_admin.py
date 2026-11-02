"""UserService tests for admin list filters/sort and mark_verified."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest


def _build_service(session, users_app_empty):
    """Build a UserService directly (bypass FastAPI Depends)."""
    from users.admin.service import UserService
    from users.db_adapter import UserDatabaseWithRoles
    from users.manager import UserManager
    from users.models import User

    user_db = UserDatabaseWithRoles(session, User)
    manager = UserManager(
        user_db,
        users_app_empty.state.users.mailer,
        users_app_empty.state.users.settings,
    )
    return UserService(session, manager)


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_users_status_disabled_filter(users_app_empty):
    """list_users(status='disabled') returns only disabled users."""
    from fastapi_users.password import PasswordHelper
    from users.models import User

    async with users_app_empty.state.sm.db.session_factory() as session:
        pw = PasswordHelper().hash("x")
        active_user = User(
            id=uuid.uuid4(),
            email="active@example.com",
            hashed_password=pw,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        disabled_user = User(
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

        svc = _build_service(session, users_app_empty)
        items, total = await svc.list_users(status="disabled")

    assert total == 1
    assert items[0].email == "disabled@example.com"


@pytest.mark.anyio
async def test_list_users_role_filter(users_app_empty):
    """list_users(role_name='admin') returns only users with that role."""
    from fastapi_users.password import PasswordHelper
    from users.constants import ADMIN_ROLE_ID
    from users.models import User, UserRole

    async with users_app_empty.state.sm.db.session_factory() as session:
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

        svc = _build_service(session, users_app_empty)
        items, total = await svc.list_users(role_name="admin")

    assert total == 1
    assert items[0].email == "role_admin@example.com"


@pytest.mark.anyio
async def test_list_users_verified_filter(users_app_empty):
    """list_users(verified='no') returns only unverified users."""
    from fastapi_users.password import PasswordHelper
    from users.models import User

    async with users_app_empty.state.sm.db.session_factory() as session:
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

        svc = _build_service(session, users_app_empty)
        items, total = await svc.list_users(verified="no")

    assert total == 1
    assert items[0].email == "unverified@example.com"


@pytest.mark.anyio
async def test_list_users_sort_last_login_desc_nulls_last(users_app_empty):
    """list_users(sort='last_login_at', order='desc') orders recent→old→never (NULLs last)."""
    from fastapi_users.password import PasswordHelper
    from users.models import User

    recent_ts = datetime(2024, 6, 1, tzinfo=UTC)
    old_ts = datetime(2023, 1, 1, tzinfo=UTC)

    async with users_app_empty.state.sm.db.session_factory() as session:
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

        svc = _build_service(session, users_app_empty)
        items, total = await svc.list_users(sort="last_login_at", order="desc")

    assert total == 3
    emails = [i.email for i in items]
    assert emails == ["recent@example.com", "old@example.com", "never@example.com"]


# ---------------------------------------------------------------------------
# mark_verified tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_mark_verified_sets_flag_and_is_idempotent(users_app_empty):
    """mark_verified sets is_verified=True and is idempotent."""
    from fastapi_users.password import PasswordHelper
    from users.models import User

    async with users_app_empty.state.sm.db.session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="unverified_mv@example.com",
            hashed_password=PasswordHelper().hash("x"),
            is_active=True,
            is_superuser=False,
            is_verified=False,
        )
        session.add(user)
        await session.flush()

        svc = _build_service(session, users_app_empty)
        result = await svc.mark_verified(user.id)
        assert result.is_verified is True

        # idempotent — second call should not raise
        result2 = await svc.mark_verified(user.id)
        assert result2.is_verified is True


@pytest.mark.anyio
async def test_mark_verified_unknown_raises(users_app_empty):
    """mark_verified raises UserNotFoundError for an unknown user_id."""
    from users.exceptions import UserNotFoundError

    async with users_app_empty.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app_empty)
        with pytest.raises(UserNotFoundError):
            await svc.mark_verified(uuid.uuid4())
