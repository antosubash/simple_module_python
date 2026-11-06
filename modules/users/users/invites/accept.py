"""Validate an invitation before atomically accepting it (#763)."""

from __future__ import annotations

import asyncio

import jwt
from fastapi import Request
from fastapi_users import exceptions
from fastapi_users.jwt import decode_jwt

from users.accounts.manager import UserManager
from users.contracts.schemas import AcceptInviteRequest
from users.models import User


async def complete_invite(
    manager: UserManager, body: AcceptInviteRequest, request: Request
) -> User:
    """Apply verification and password together; preserve both lifecycle hooks."""
    # Match BaseUserManager.verify's token checks without its committing write.
    try:
        data = decode_jwt(
            body.token, manager.verification_token_secret, [manager.verification_token_audience]
        )
        user_id, email = data["sub"], data["email"]
        if not isinstance(user_id, str) or not isinstance(email, str):
            raise exceptions.InvalidVerifyToken()
        user = await manager.get_by_email(email)
        parsed_id = manager.parse_id(user_id)
    except (jwt.PyJWTError, KeyError, exceptions.UserNotExists, exceptions.InvalidID):
        raise exceptions.InvalidVerifyToken() from None
    if parsed_id != user.id:
        raise exceptions.InvalidVerifyToken()
    if user.is_verified:
        raise exceptions.UserAlreadyVerified()

    await manager.validate_password(body.password, user)
    # A blank name keeps what the admin typed when minting the invite: the form is
    # pre-filled from it, so an untouched field must not read as "clear this".
    profile: dict[str, str] = {}
    if body.full_name and body.full_name.strip():
        profile["full_name"] = body.full_name.strip()
    hashed_password = await asyncio.to_thread(manager.password_helper.hash, body.password)
    user = await manager.user_db.update(
        user, {**profile, "hashed_password": hashed_password, "is_verified": True}
    )
    await manager.on_after_verify(user, request)
    await manager.on_after_update(user, {"password": body.password, **profile}, request)
    return user
