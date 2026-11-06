"""Shared builders for the admin API and service tests."""

from __future__ import annotations

import uuid

from fastapi_users.password import PasswordHelper
from users.models import Role, User, UserRole

_pw = PasswordHelper()


async def _make_user(session, email, password="SecurePass1!", verified=True, role_names=None):
    from sqlalchemy import select

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pw.hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=verified,
    )
    session.add(user)
    await session.flush()

    if role_names:
        roles = (
            (await session.execute(select(Role).where(Role.name.in_(role_names)))).scalars().all()
        )
        for role in roles:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    await session.commit()
    await session.refresh(user)
    return user


def _build_service(session, users_app_empty):
    """Build a UserService directly (bypass FastAPI Depends)."""
    from users.accounts.db_adapter import UserDatabaseWithRoles
    from users.accounts.manager import UserManager
    from users.admin.service import UserService
    from users.models import User

    user_db = UserDatabaseWithRoles(session, User)
    manager = UserManager(
        user_db,
        users_app_empty.state.users.mailer,
        users_app_empty.state.users.settings,
    )
    return UserService(session, manager)
