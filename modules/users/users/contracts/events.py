"""Public events published by the users module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass
class UserRegistered(Event):
    user_id: uuid.UUID
    email: str


@dataclass
class UserInvited(Event):
    user_id: uuid.UUID
    email: str
    invited_by: str | None


@dataclass
class UserDisabled(Event):
    user_id: uuid.UUID


@dataclass
class RoleAssigned(Event):
    user_id: uuid.UUID
    role_name: str
