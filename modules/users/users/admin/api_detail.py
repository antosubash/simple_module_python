"""Admin REST reads and unlink that mirror the Edit page's data (#1178).

Mounted under the admin router in ``api.py``, so every route inherits the
``users.manage`` guard. They reuse the Edit page's service calls.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import status as http_status
from simple_module_db.engine.deps import get_db
from simple_module_hosting.auth.csrf import RequiresCsrf
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from users.admin.linked_sign_ins import linked_sign_ins_for
from users.admin.presenters import roles_payload
from users.admin.service import UserService
from users.contracts.schemas import UserListItem
from users.core.exceptions import UserNotFoundError
from users.web.deps import get_user_service

detail_router = APIRouter()


class RoleOption(SQLModel):
    id: str
    name: str


class LinkedSignIn(SQLModel):
    id: str
    provider: str
    username: str | None = None
    subject: str | None = None
    last_sign_in_at: str | None = None


class LinkedSignInList(SQLModel):
    linked_sign_ins: list[LinkedSignIn]
    has_duplicate_linked_sign_ins: bool


@detail_router.get("/roles", response_model=list[RoleOption])
async def admin_list_roles(request: Request):
    """Assignable roles, as the Edit page's ``roles`` prop."""
    return await roles_payload(request.app)


@detail_router.get("/{user_id}", response_model=UserListItem)
async def admin_get_user(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """One user, as the Edit page's ``user`` prop."""
    try:
        return await service.get_list_item(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None


@detail_router.get("/{user_id}/linked-sign-ins", response_model=LinkedSignInList)
async def admin_list_linked_sign_ins(
    user_id: uuid.UUID,
    request: Request,
    service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db),
):
    """External sign-ins linked to a user."""
    try:
        await service.get_list_item(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    links, has_duplicates = await linked_sign_ins_for(request, user_id, db)
    return LinkedSignInList(
        linked_sign_ins=[LinkedSignIn(**link) for link in links],
        has_duplicate_linked_sign_ins=has_duplicates,
    )


@detail_router.delete(
    "/{user_id}/linked-sign-ins/{link_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RequiresCsrf())],
)
async def admin_unlink_sign_in_api(
    user_id: uuid.UUID,
    link_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Unlink one sign-in; another user's link is a 404 (same rules as the view)."""
    try:
        await service.unlink_sign_in(user_id, link_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
