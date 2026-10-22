"""DTOs for the retained-log screens (GH #537)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from simple_module_db.types import AwareDateTime
from sqlmodel import Field, SQLModel


class LogItem(SQLModel):
    id: uuid.UUID
    ts: datetime = Field(sa_type=AwareDateTime())
    level: int
    level_name: str
    logger: str
    message: str
    task_id: str | None = None
    job_id: str | None = None
    tenant_id: str | None = None
    correlation_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LogListResponse(SQLModel):
    items: list[LogItem]
    total: int
    page: int
    per_page: int
