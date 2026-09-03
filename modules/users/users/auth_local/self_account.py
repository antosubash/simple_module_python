"""What you can do to your own account from the profile page.

``POST /api/users/me/password``          — change your password
``POST /api/users/me/sessions/revoke-all`` — sign out everywhere

Split out of ``api.py`` (which is at the 300-line cap) because these are the
account-owner's actions rather than the sign-in machinery: they assume a
session already exists and act on the account behind it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi_users import exceptions as fu_exceptions
from simple_module_db.deps import get_db
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from users.contracts.schemas import SelfPasswordChange, UserUpdate
from users.deps import fastapi_users, get_user_manager
from users.manager import UserManager
from users.models import RefreshToken, UserAccessToken

router = APIRouter()


@router.post("/me/password", status_code=204)
async def change_my_password(
    body: SelfPasswordChange,
    request: Request,
    user=Depends(fastapi_users.current_user(active=True)),
    user_manager: UserManager = Depends(get_user_manager),
) -> Response:
    """Change your own password, proving you know the current one.

    A live session is not proof enough: an unattended browser is exactly what
    this guards against, and re-asking is the only thing that distinguishes
    the account's owner from whoever sat down next.

    400 rather than 403 for an SSO account: there is no password here to be
    forbidden from changing, so this is a bad request about a field that does
    not apply, not an authorisation decision.
    """
    if user.is_external or user.hashed_password is None:
        raise HTTPException(
            status_code=400,
            detail="This account signs in through an identity provider and has no password here.",
        )

    verified, _ = user_manager.password_helper.verify_and_update(
        body.current_password, user.hashed_password
    )
    if not verified:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    try:
        await user_manager.update(UserUpdate(password=body.new_password), user, request=request)
    except fu_exceptions.InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    return Response(status_code=204)


@router.post("/me/sessions/revoke-all", status_code=204)
async def revoke_all_my_sessions(
    request: Request,
    user=Depends(fastapi_users.current_user(active=True)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Sign this account out of every browser and client, including this one.

    Browser auth is a signed cookie rather than a row, so there is nothing to
    delete for a laptop left on a train. Bumping ``session_version`` strands
    every session stamped with the old value wherever it is; the access-token
    rows and the refresh tokens are the bearer half of the same idea and go
    with it. The caller is signed out too — anything else would leave the one
    session that ordered the revocation as the exception to it.
    """
    now = datetime.now(UTC)
    # Bumped through the ORM rather than as a bulk UPDATE: a Core statement
    # does not mark the request session as written, so ``get_db`` would treat
    # this handler as read-only and roll the whole revocation back. ``user``
    # is already attached to this session — ``get_user_db`` takes the same
    # ``get_db`` dependency — so the assignment is enough.
    user.session_version = int(user.session_version or 0) + 1
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(delete(UserAccessToken).where(UserAccessToken.user_id == user.id))
    await db.flush()

    request.session.clear()
    response = Response(status_code=204)
    response.delete_cookie(request.app.state.users.settings.cookie_name, path="/")
    return response
