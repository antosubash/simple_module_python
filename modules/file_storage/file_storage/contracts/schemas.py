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


class BulkDeleteRequest(SQLModel):
    """Body for POST /api/file-storage/files/bulk-delete."""

    # Bounded for the same reason ``per_page`` is: the ids land in a single
    # ``IN (...)``, and an unbounded list lets one request build a statement
    # large enough to be refused by the driver rather than by us. The screen
    # selects at most one page, so the page-size ceiling is the natural bound.
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class BulkDeleteResult(SQLModel):
    """How many rows the batch actually removed.

    Not simply ``len(ids)``: a selection can name files another admin has
    already deleted, and the caller's toast should say what happened.
    """

    deleted: int


class StoredFileListOut(SQLModel):
    """Paginated list response."""

    items: list[StoredFileOut]
    total: int
    page: int
    per_page: int
