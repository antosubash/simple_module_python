"""Admin REST endpoints for the users module.

Split out of :mod:`.api` to keep per-file complexity manageable. Mounted
into the main ``router`` via ``include_router`` at the bottom of ``api.py``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from simple_module_core.events import EventBus
from simple_module_hosting.permissions import RequiresPermission

from users.contracts.events import RoleAssigned, UserDisabled, UserInvited
from users.contracts.schemas import (
    PasswordResetLink,
    RoleAssignment,
    UserInvite,
    UserListItem,
)
from users.deps import get_event_bus, get_mailer, get_user_service
from users.service import UserService

admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(RequiresPermission("users.manage"))],
    tags=["users-admin"],
)


@admin_router.get("", response_model=list[UserListItem])
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    service: UserService = Depends(get_user_service),
):
    """List all users (paginated, optional search)."""
    items, _ = await service.list_users(page=page, per_page=per_page, search=q)
    return items


@admin_router.post(
    "/invite",
    response_model=UserListItem,
    status_code=status.HTTP_201_CREATED,
)
async def admin_invite_user(
    data: UserInvite,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
    mailer=Depends(get_mailer),
):
    """Invite a new user by email, optionally assigning roles."""
    invited_by = getattr(request.state, "user", None)
    invited_by_name = invited_by.name if invited_by else "Administrator"
    user, token = await service.invite(
        data.email, data.full_name, data.role_names, invited_by=invited_by
    )
    await mailer.send_invite(user.email, token, invited_by_name)
    await bus.publish(
        UserInvited(
            user_id=user.id,
            email=user.email,
            invited_by=(str(invited_by.id) if invited_by else None),
        )
    )
    return await service.to_list_item(user)


@admin_router.patch("/{user_id}/disable", response_model=UserListItem)
async def admin_disable_user(
    user_id: uuid.UUID,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Disable a user account (sets is_active=False and disabled_at)."""
    user = await service.disable(user_id)
    await bus.publish(UserDisabled(user_id=user.id))
    return await service.to_list_item(user)


@admin_router.patch("/{user_id}/enable", response_model=UserListItem)
async def admin_enable_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Re-enable a previously disabled user account."""
    user = await service.enable(user_id)
    return await service.to_list_item(user)


@admin_router.put("/{user_id}/roles", response_model=UserListItem)
async def admin_set_roles(
    user_id: uuid.UUID,
    data: RoleAssignment,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Replace a user's role assignments."""
    assigned_by = getattr(request.state, "user", None)
    user = await service.set_roles(
        user_id,
        data.role_names,
        assigned_by=str(assigned_by.id) if assigned_by else None,
    )
    for role in data.role_names:
        await bus.publish(RoleAssigned(user_id=user.id, role_name=role))
    return await service.to_list_item(user)


@admin_router.post("/{user_id}/reset-password-link", response_model=PasswordResetLink)
async def admin_reset_password_link(
    user_id: uuid.UUID,
    request: Request,
    service: UserService = Depends(get_user_service),
):
    """Generate a password-reset link for the given user (admin copy)."""
    base_url = request.app.state.users_settings.base_url
    link = await service.generate_reset_link(user_id, base_url)
    return PasswordResetLink(link=link)
