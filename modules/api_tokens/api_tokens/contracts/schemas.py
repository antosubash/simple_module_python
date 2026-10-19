"""SQLModel DTOs for the api_tokens module — its public surface."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict, field_validator
from sqlmodel import Field, SQLModel

from api_tokens.constants import MAX_SCOPES, NAME_MAX_LENGTH


class TokenView(SQLModel):
    """A token as lists show it. Never carries the secret or its hash."""

    model_config = ConfigDict(from_attributes=True)  # ty: ignore[invalid-assignment]

    id: uuid.UUID
    kind: str
    name: str
    prefix: str
    scopes: list[str]
    roles: list[str] = []
    owner_user_id: uuid.UUID | None = None
    owner_email: str | None = None
    tenant_id: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None
    expires_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class CreatedToken(SQLModel):
    """The one response that carries the plaintext token."""

    token: str
    item: TokenView


class _CreateBase(SQLModel):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    scopes: list[str] = Field(min_length=1, max_length=MAX_SCOPES)
    # Bounded above by the ``max_lifetime_days`` setting, checked in the service.
    expires_in_days: int = Field(ge=1)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class PersonalTokenCreate(_CreateBase):
    """Create a personal access token for the signed-in user."""


class ServiceKeyCreate(_CreateBase):
    """Create a service key. ``roles`` may not include ``admin``."""

    roles: list[str] = Field(default_factory=list, max_length=50)


class RevokedCount(SQLModel):
    """How many tokens a bulk revoke ended."""

    revoked: int
