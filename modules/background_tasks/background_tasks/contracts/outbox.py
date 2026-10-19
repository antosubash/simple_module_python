"""DTOs for the durable-event outbox admin API and page (GH #459)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import ConfigDict
from sqlmodel import SQLModel

from background_tasks.constants import OutboxStatus


class OutboxItem(SQLModel):
    """One (event, durable handler) delivery as the admin screen shows it."""

    model_config = ConfigDict(from_attributes=True)  # ty: ignore[invalid-assignment]

    id: uuid.UUID
    event_key: str
    handler_name: str
    payload: dict[str, Any] = {}
    tenant_id: str | None = None
    status: OutboxStatus
    attempts: int
    next_attempt_at: datetime
    locked_until: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None


class OutboxListResponse(SQLModel):
    items: list[OutboxItem]
    total: int
    page: int
    per_page: int
    # Undelivered rows per status, for the tiles above the table.
    counts: dict[str, int]
