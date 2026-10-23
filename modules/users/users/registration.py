"""Request-bound registration helpers shared by the ``UserManager`` hooks."""

from __future__ import annotations

import logging

from simple_module_db import independent_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.constants import USER_ROLE_NAME
from users.models import Role, User, UserRole

logger = logging.getLogger(__name__)


async def attach_default_role(session: AsyncSession, user: User) -> None:
    """Give a self-registered (or OAuth-provisioned) user the ``user`` role.

    Without it a fresh signup holds no permissions at all — not even
    ``api_tokens.use`` — until an admin assigns a role by hand (GH #488).
    Only request-bound registrations reach here: the admin create and
    invite flows call ``create()`` with no request and assign exactly the
    roles the admin picked, which may deliberately be none.

    Looked up, never created: migration ``b5018b617142`` seeds it on a
    fresh install, so a missing one means an admin deleted it, and a
    public signup must not undo that. It also keeps concurrent signups
    from racing to insert it.
    """
    async with independent_session(session) as checkpoint:
        role = (
            await checkpoint.execute(select(Role).where(col(Role.name) == USER_ROLE_NAME))
        ).scalar_one_or_none()
        if role is None:
            logger.warning(
                "No '%s' role exists; %s registered with no role", USER_ROLE_NAME, user.id
            )
            return
        # fastapi-users already committed the account. Keep its default role
        # even if a later registration hook or verification email fails.
        checkpoint.add(UserRole(user_id=user.id, role_id=role.id))
