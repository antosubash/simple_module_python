"""Admin REST endpoints for the users module."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import status as http_status
from fastapi_users import exceptions as fa_exceptions
from simple_module_core.events import EventBus
from simple_module_hosting.permissions import RequiresPermission

from users.admin.bulk_invite import bulk_router
from users.admin.service import UserService
from users.constants import PERM_USERS_MANAGE, sanitize_list_filters
from users.contracts.events import (
    RoleAssigned,
    UserCreated,
    UserDeleted,
    UserDisabled,
    UserInvited,
)
from users.contracts.schemas import (
    PasswordResetLink,
    RoleAssignment,
    UserAdminCreate,
    UserDetailsUpdate,
    UserInvite,
    UserListItem,
)
from users.deps import get_event_bus, get_mailer, get_user_service
from users.exceptions import (
    EmailAlreadyExistsError,
    ExternalUserNoPasswordError,
    UserNotFoundError,
)

admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
    tags=["users-admin"],
)

# Bulk invite lives in its own module (this file is near the 300-line cap) but
# mounts here so it inherits the users.manage guard above.
admin_router.include_router(bulk_router)


@admin_router.get("", response_model=list[UserListItem])
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    verified: str | None = None,
    sort: str = "email",
    order: str = "asc",
    service: UserService = Depends(get_user_service),
):
    """List all users (paginated, optional search and filters)."""
    _status, _verified, _sort, _order = sanitize_list_filters(status, verified, sort, order)
    items, _ = await service.list_users(
        page=page,
        per_page=per_page,
        search=q,
        status=_status,
        role_name=role or None,
        verified=_verified,
        sort=_sort,
        order=_order,
    )
    return items


@admin_router.post(
    "/invite",
    response_model=UserListItem,
    status_code=http_status.HTTP_201_CREATED,
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
    return service.to_list_item(user)


@admin_router.post(
    "",
    response_model=UserListItem,
    status_code=http_status.HTTP_201_CREATED,
)
async def admin_create_user(
    data: UserAdminCreate,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Create an active+verified user with an admin-set password."""
    creator = getattr(request.state, "user", None)
    created_by = str(creator.id) if creator else None
    try:
        user = await service.create_user(
            data.email,
            data.password,
            data.full_name,
            data.role_names,
            created_by=created_by,
        )
    except fa_exceptions.UserAlreadyExists:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists.",
        ) from None
    except fa_exceptions.InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from None
    await bus.publish(UserCreated(user_id=user.id, email=user.email, created_by=created_by))
    return service.to_list_item(user)


@admin_router.patch("/{user_id}", response_model=UserListItem)
async def admin_update_user(
    user_id: uuid.UUID,
    data: UserDetailsUpdate,
    service: UserService = Depends(get_user_service),
):
    """Update a user's email and full name."""
    try:
        user = await service.update_details(user_id, data.email, data.full_name)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists.",
        ) from None
    return service.to_list_item(user)


@admin_router.delete("/{user_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: uuid.UUID,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Hard-delete a user. An admin cannot delete their own account."""
    actor = getattr(request.state, "user", None)
    if actor is not None and str(user_id) == actor.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )
    try:
        await service.delete_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    await bus.publish(UserDeleted(user_id=user_id))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@admin_router.patch("/{user_id}/disable", response_model=UserListItem)
async def admin_disable_user(
    user_id: uuid.UUID,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Disable a user account (sets is_active=False and disabled_at)."""
    try:
        user = await service.disable(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    await bus.publish(UserDisabled(user_id=user.id))
    return service.to_list_item(user)


@admin_router.patch("/{user_id}/enable", response_model=UserListItem)
async def admin_enable_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Re-enable a previously disabled user account."""
    try:
        user = await service.enable(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    return service.to_list_item(user)


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
    try:
        user = await service.set_roles(
            user_id,
            data.role_names,
            assigned_by=str(assigned_by.id) if assigned_by else None,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    for role in data.role_names:
        await bus.publish(RoleAssigned(user_id=user.id, role_name=role))
    return service.to_list_item(user)


@admin_router.patch("/{user_id}/verify", response_model=UserListItem)
async def admin_mark_verified(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Mark a user verified. Idempotent."""
    try:
        user = await service.mark_verified(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    return service.to_list_item(user)


@admin_router.post("/{user_id}/reset-password-link", response_model=PasswordResetLink)
async def admin_reset_password_link(
    user_id: uuid.UUID,
    request: Request,
    service: UserService = Depends(get_user_service),
):
    """Generate a password-reset link for the given user (admin copy)."""
    base_url = request.app.state.users.settings.base_url
    try:
        link = await service.generate_reset_link(user_id, base_url)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except ExternalUserNoPasswordError:
        raise HTTPException(
            status_code=409,
            detail="External (SSO) users have no password to reset",
        ) from None
    return PasswordResetLink(link=link)
