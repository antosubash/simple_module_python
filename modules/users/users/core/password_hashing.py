"""Async crypto boundaries for fastapi-users 15's synchronous password helper."""

from __future__ import annotations

import asyncio
from typing import Any

import jwt
from fastapi import Request
from fastapi_users import exceptions
from fastapi_users.jwt import decode_jwt
from fastapi_users.password import PasswordHelper

from users.contracts.schemas import UserCreate
from users.models import User

PASSWORD_HELPER = PasswordHelper()


class PasswordHashingMixin:
    """Keep validation, database operations and lifecycle hooks on the event loop."""

    async def create(
        self,
        user_create: UserCreate,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        await self.validate_password(user_create.password, user_create)
        if await self.user_db.get_by_email(user_create.email) is not None:
            raise exceptions.UserAlreadyExists()
        data = (
            user_create.create_update_dict() if safe else user_create.create_update_dict_superuser()
        )
        password = data.pop("password")
        data["hashed_password"] = await asyncio.to_thread(self.password_helper.hash, password)
        user = await self.user_db.create(data)
        await self.on_after_register(user, request)
        return user

    async def _update(self, user: User, update_dict: dict[str, Any]) -> User:
        # Let upstream handle email uniqueness and every non-password field.
        data = dict(update_dict)
        if data.get("password") is not None:
            password = data.pop("password")
            await self.validate_password(password, user)
            data["hashed_password"] = await asyncio.to_thread(self.password_helper.hash, password)
        return await super()._update(user, data)

    async def reset_password(
        self, token: str, password: str, request: Request | None = None
    ) -> User:
        # Mirrors upstream token/fingerprint checks; only crypto leaves the loop.
        try:
            data = decode_jwt(
                token, self.reset_password_token_secret, [self.reset_password_token_audience]
            )
            user_id = data["sub"]
            fingerprint = data["password_fgpt"]
            parsed_id = self.parse_id(user_id)
        except (jwt.PyJWTError, KeyError, exceptions.InvalidID):
            raise exceptions.InvalidResetPasswordToken() from None
        user = await self.get(parsed_id)
        valid, _ = await asyncio.to_thread(
            self.password_helper.verify_and_update, user.hashed_password, fingerprint
        )
        if not valid:
            raise exceptions.InvalidResetPasswordToken()
        if not user.is_active:
            raise exceptions.UserInactive()
        updated = await self._update(user, {"password": password})
        await self.on_after_reset_password(updated, request)
        return updated
