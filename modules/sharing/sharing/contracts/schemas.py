"""Sharing DTOs — the module's public surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from simple_module_core.resources import ACTION_VIEW
from sqlmodel import Field, SQLModel

from sharing.core.constants import (
    RESOURCE_ID_MAX,
    RESOURCE_TYPE_MAX,
    ROLE_MAX,
    SUBJECT_ID_MAX,
    SUBJECT_USER,
)


class ShareGrant(SQLModel):
    """Grant (or update) one user's access to one resource."""

    resource_type: str = Field(min_length=1, max_length=RESOURCE_TYPE_MAX)
    resource_id: str = Field(min_length=1, max_length=RESOURCE_ID_MAX)
    subject_id: str = Field(min_length=1, max_length=SUBJECT_ID_MAX)
    subject_type: Literal["user"] = SUBJECT_USER
    role: str = Field(default=ACTION_VIEW, max_length=ROLE_MAX)
    expires_at: datetime | None = None


class ShareCandidate(SQLModel):
    id: str
    display_name: str
    email: str


class ShareOut(SQLModel):
    id: uuid.UUID
    resource_type: str
    resource_id: str
    subject_type: str
    subject_id: str
    subject_label: str | None = None
    role: str
    granted_by: str
    granted_by_label: str | None = None
    expires_at: datetime | None = None
    expired: bool = False
    created_at: datetime | None = None
