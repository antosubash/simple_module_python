"""Public dependencies and the FastAPIUsers instance.

Cookie transport and auth backend are constructed at import time with
dev-safe defaults (cookie_secure=False, dev cookie name). UsersModule.on_startup
overrides the cookie params from the real UsersSettings once app.state is
populated — CookieTransport's cookie fields are mutable on the instance.

The singleton is here rather than in register_routes because
``current_active_user`` and ``current_superuser`` are decorator-factories
that must be resolvable at import time for route-handler signatures.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from fastapi_users import FastAPIUsers
from simple_module_core.events import EventBus
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from users.backend import build_auth_backend, build_cookie_transport
from users.db_adapter import (
    UserDatabaseWithRoles,
    get_access_token_db,
    get_user_db,
)
from users.manager import UserManager, get_user_manager
from users.models import User

if TYPE_CHECKING:
    from users.service import UserService

# Dev-safe singleton — UsersModule patches cookie params at startup.
_cookie_transport = build_cookie_transport(
    cookie_name="sm_auth",
    cookie_max_age_seconds=60 * 60 * 24 * 14,
    cookie_secure=False,  # host flips True in production via register_routes
    cookie_samesite="lax",
)
auth_backend = build_auth_backend(_cookie_transport)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)


def get_mailer(request: Request):
    """Return the mailer from app.state (built in UsersModule.on_startup)."""
    return request.app.state.mailer


def get_event_bus(request: Request) -> EventBus:
    """Return the event bus from app.state."""
    return request.app.state.event_bus


async def get_user_service(
    db: AsyncSession = Depends(get_db),
    user_manager: UserManager = Depends(get_user_manager),
) -> UserService:
    from users.service import UserService

    return UserService(db, user_manager)


__all__ = [
    "UserDatabaseWithRoles",
    "UserManager",
    "auth_backend",
    "current_active_user",
    "current_superuser",
    "fastapi_users",
    "get_access_token_db",
    "get_event_bus",
    "get_mailer",
    "get_user_db",
    "get_user_manager",
    "get_user_service",
]
