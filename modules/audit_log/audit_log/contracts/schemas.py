"""SQLModel DTOs for the Audit Log module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class AuditEntryRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: str
    action: str
    changes: list[dict]
    user_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime


class AuditEntryList(SQLModel):
    items: list[AuditEntryRead]
    total: int
    page: int
    page_size: int
