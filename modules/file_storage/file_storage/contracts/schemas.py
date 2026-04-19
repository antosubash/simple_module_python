"""SQLModel DTOs for the file_storage module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class StoredFileOut(SQLModel):
    """Metadata returned for a stored file."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    filename: str
    content_type: str
    size_bytes: int
    backend: str
    checksum_sha256: str
    uploaded_by: str | None = Field(
        default=None,
        description="User id from AuditMixin.created_by — populated by the audit listener.",
    )
    created_at: datetime | None = None


class StoredFileListOut(SQLModel):
    """Paginated list response."""

    items: list[StoredFileOut]
    total: int
    page: int
    per_page: int
