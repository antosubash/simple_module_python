"""SQLModel DTOs for the Audit Log module."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class AuditEntryRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    entity_type: str
    entity_id: str
    action: str
    changes: list[dict]
    user_id: str | None = None
    correlation_id: str | None = None
    created_at: datetime | None = None


class AuditEntryList(SQLModel):
    items: list[AuditEntryRead]
    total: int
    page: int
    page_size: int
