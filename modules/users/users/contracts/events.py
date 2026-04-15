"""Public events published by the users module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class UserRegistered:
    user_id: uuid.UUID
    email: str


@dataclass(frozen=True)
class UserInvited:
    user_id: uuid.UUID
    email: str
    invited_by: str | None


@dataclass(frozen=True)
class UserDisabled:
    user_id: uuid.UUID


@dataclass(frozen=True)
class RoleAssigned:
    user_id: uuid.UUID
    role_name: str
