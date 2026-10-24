"""Authorization and administrator availability for admin writes (#624)."""

import uuid

from auth.contracts.schemas import UserContext
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.admin.queries import _UserServiceBase
from users.constants import ADMIN_ROLE_NAME
from users.exceptions import AdminAccountSafetyError, AdminPermissionError
from users.manager import UserManager
from users.models import Role, User, UserRole


def _is_admin(actor: UserContext) -> bool:
    return ADMIN_ROLE_NAME in actor.roles


def check_role_assignment(actor: UserContext | None, role_names: list[str]) -> None:
    """Refuse a grant wider than the actor's own authority.

    ``None`` is reserved for trusted in-process callers; HTTP always supplies an
    actor. A full admin session grants anything; an admin's scoped token (PAT,
    bearer) grants anything except ``admin`` itself; anyone else only roles they
    hold.
    """
    if actor is None or (_is_admin(actor) and not actor.is_scoped):
        return
    if _is_admin(actor):
        if ADMIN_ROLE_NAME in role_names:
            raise AdminPermissionError("You cannot assign roles you do not hold.")
        return
    if not set(role_names).issubset(actor.roles):
        raise AdminPermissionError("You cannot assign roles you do not hold.")


class _UserAdminSafety(_UserServiceBase):
    def __init__(
        self,
        db: AsyncSession,
        user_manager: UserManager,
        app: FastAPI | None = None,
        *,
        actor: UserContext | None = None,
    ) -> None:
        super().__init__(db, user_manager, app)
        self._actor = actor

    async def _require_manageable_user(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        actor = self._actor
        if actor is None or (_is_admin(actor) and not actor.is_scoped):
            return user
        roles = {role.name for role in user.roles}
        privileged = user.is_superuser or ADMIN_ROLE_NAME in roles
        # An admin's scoped token manages ordinary accounts, never another admin.
        stronger = not _is_admin(actor) and not roles.issubset(actor.roles)
        if privileged or stronger:
            raise AdminPermissionError("You cannot manage a more privileged account.")
        return user

    async def _guard_admin_removal(self, user: User) -> None:
        if self._actor is not None and str(user.id) == self._actor.id:
            raise AdminAccountSafetyError("You cannot disable or demote your own account.")
        if not user.is_active or user.disabled_at is not None:
            return
        if not user.is_superuser and ADMIN_ROLE_NAME not in {r.name for r in user.roles}:
            return

        # Serialize destructive admin operations on Postgres before counting survivors.
        await self._db.execute(
            select(Role.id).where(Role.name == ADMIN_ROLE_NAME).with_for_update()
        )
        admin_ids = (
            select(UserRole.user_id)
            .join(Role, col(Role.id) == UserRole.role_id)
            .where(Role.name == ADMIN_ROLE_NAME)
        )
        remaining = await self._db.execute(
            select(User.id)
            .where(
                col(User.id) != user.id,
                col(User.is_active).is_(True),
                col(User.disabled_at).is_(None),
                col(User.id).in_(admin_ids),
            )
            .limit(1)
        )
        if remaining.scalar_one_or_none() is None:
            raise AdminAccountSafetyError("You cannot remove the last active administrator.")
