"""Authorization and administrator availability for admin writes (#624)."""

import uuid

from auth.contracts.schemas import UserContext
from fastapi import FastAPI, Request
from simple_module_core.app_state import get_services
from simple_module_core.permissions import DEFAULT_ROLE_PERMISSIONS, grants
from simple_module_hosting.permissions import (
    apply_scope_cap,
    ensure_resolved_permissions,
    resolve_permissions,
    resolve_principal_permissions,
)
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


def _is_full_admin(actor: UserContext | None) -> bool:
    """``None`` is a trusted in-process caller; an unscoped admin holds everything."""
    return actor is None or (_is_admin(actor) and not actor.is_scoped)


def _covers(held: set[str], wanted: set[str]) -> bool:
    return all(grants(held, permission) for permission in wanted)


def check_role_assignment(
    actor: UserContext | None,
    role_names: list[str],
    actor_permissions: set[str],
    role_map: dict[str, list[str]],
) -> None:
    """Refuse a grant wider than the actor's effective permissions.

    ``actor_permissions`` is what the request's authorization resolved for the
    actor (roles, direct grants, token-scope cap). Every requested role's
    permissions must be covered; ``admin`` maps to the wildcard, so only a
    principal holding the wildcard itself can grant it. A full admin session
    (and ``None``, a trusted in-process caller) is unrestricted.
    """
    if _is_full_admin(actor):
        return
    wanted = resolve_permissions(role_names, role_map)
    if ADMIN_ROLE_NAME in role_names or not _covers(actor_permissions, wanted):
        raise AdminPermissionError("You cannot assign roles you do not hold.")


async def check_request_role_assignment(request: Request, role_names: list[str]) -> None:
    """:func:`check_role_assignment` for the request's own principal."""
    actor = getattr(request.state, "user", None)
    if _is_full_admin(actor):
        return
    registry = getattr(get_services(request.app), "permissions", None)
    role_map = registry.role_map if registry is not None else DEFAULT_ROLE_PERMISSIONS
    check_role_assignment(actor, role_names, await ensure_resolved_permissions(request), role_map)


class _UserAdminSafety(_UserServiceBase):
    def __init__(
        self,
        db: AsyncSession,
        user_manager: UserManager,
        app: FastAPI | None = None,
        *,
        actor: UserContext | None = None,
        request: Request | None = None,
    ) -> None:
        super().__init__(db, user_manager, app)
        self._actor = actor
        self._request = request

    def _role_map(self) -> dict[str, list[str]]:
        sm = get_services(self._app) if self._app is not None else None
        registry = getattr(sm, "permissions", None)
        return registry.role_map if registry is not None else DEFAULT_ROLE_PERMISSIONS

    async def _actor_permissions(self) -> set[str]:
        actor = self._actor
        if actor is None:
            return set()
        if self._request is not None:
            return await ensure_resolved_permissions(self._request)
        return apply_scope_cap(resolve_permissions(actor.roles, self._role_map()), actor)

    async def _target_permissions(self, user: User) -> set[str]:
        """Roles plus direct grants, resolved the way a request as *user* would."""
        principal = UserContext.from_user(user)
        if self._request is not None:
            sm = get_services(self._request.app)
            registry = getattr(sm, "permissions", None)
            return await resolve_principal_permissions(self._request, principal, registry)
        return resolve_permissions(principal.roles, self._role_map())

    async def _check_roles(self, role_names: list[str]) -> None:
        if _is_full_admin(self._actor):
            return
        check_role_assignment(
            self._actor, role_names, await self._actor_permissions(), self._role_map()
        )

    async def _require_manageable_user(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        if _is_full_admin(self._actor):
            return user
        roles = {role.name for role in user.roles}
        if user.is_superuser or ADMIN_ROLE_NAME in roles:
            raise AdminPermissionError("You cannot manage a more privileged account.")
        held = await self._actor_permissions()
        if not _covers(held, await self._target_permissions(user)):
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
