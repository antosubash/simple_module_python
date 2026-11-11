"""Request-bound registration helpers shared by the ``UserManager`` hooks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from simple_module_db import independent_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.core.constants import USER_ROLE_NAME
from users.models import Role, User, UserRole

if TYPE_CHECKING:
    from users.core.settings import UsersSettings

logger = logging.getLogger(__name__)


def registration_role(settings: UsersSettings, oauth_provider: str | None) -> str | None:
    """The role a request-bound registration gets, or ``None`` for no role.

    Local self-signup gets ``user``. An account created through a provider in
    ``oauth_signup_providers`` gets ``oauth_signup_default_role`` (none when
    blank), even with signup open, so listing a provider never widens it (#874).
    Any other OAuth-provisioned account gets ``user`` only with signup open:
    with signups closed it waits for an admin (#543).
    """
    if oauth_provider is None:
        return USER_ROLE_NAME
    if oauth_provider in settings.oauth_signup_providers:
        return settings.oauth_signup_default_role or None
    return USER_ROLE_NAME if settings.allow_signup else None


async def attach_default_role(
    session: AsyncSession, user: User, role_name: str = USER_ROLE_NAME
) -> None:
    """Give a self-registered (or OAuth-provisioned) user ``role_name``.

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
    user_id = user.id
    # End fastapi-users' post-commit refresh transaction before borrowing again.
    # Framework sessions keep objects loaded on commit for the remaining hooks.
    await session.commit()
    async with independent_session(session) as checkpoint:
        role = (
            await checkpoint.execute(select(Role).where(col(Role.name) == role_name))
        ).scalar_one_or_none()
        if role is None:
            logger.warning("No '%s' role exists; %s registered with no role", role_name, user_id)
            return
        # fastapi-users already committed the account. Keep its default role
        # even if a later registration hook or verification email fails.
        checkpoint.add(UserRole(user_id=user_id, role_id=role.id))
