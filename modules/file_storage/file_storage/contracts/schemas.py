"""SQLModel DTOs for the file_storage module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import ConfigDict, StrictBool
from sqlmodel import Field, SQLModel


class StoredFileOut(SQLModel):
    """Metadata returned for a stored file."""

    model_config = ConfigDict(from_attributes=True)  # ty: ignore[invalid-assignment]

    id: uuid.UUID
    key: str
    filename: str
    content_type: str
    size_bytes: int
    backend: str
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256, or null for a multipart upload not yet hashed.",
    )
    uploaded_by: str | None = Field(
        default=None,
        description="User id from AuditMixin.created_by — populated by the audit listener.",
    )
    created_at: datetime | None = None
    public: bool = Field(default=False, description="Whether anonymous visitors may fetch it.")
    public_url: str | None = Field(
        default=None,
        description="Anonymous URL, present only while the file is public.",
    )


class StoredFileUpdate(SQLModel):
    """Body for PATCH /api/file-storage/files/{id}."""

    # Strict: a JSON body says ``true``/``false``. Lax coercion would publish a
    # file on ``"yes"``, ``"true"`` or ``1`` from a client bug. The upload form
    # stays lax on purpose — multipart values are always strings.
    public: StrictBool


class BulkDeleteRequest(SQLModel):
    """Body for POST /api/file-storage/files/bulk-delete."""

    # Bounded for the same reason ``per_page`` is: the ids land in a single
    # ``IN (...)``, and an unbounded list lets one request build a statement
    # large enough to be refused by the driver rather than by us. The screen
    # selects at most one page, so the page-size ceiling is the natural bound.
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class BulkDeleteResult(SQLModel):
    """Which rows the batch actually removed.

    Not simply an echo of the request: a selection can name files another admin
    has already deleted. The caller needs the ids, not only the count — a
    screen that names "the" deleted file from its own selection would credit
    the wrong filename whenever part of the batch had already gone.
    """

    deleted: int
    ids: list[uuid.UUID] = Field(default_factory=list)


class StoredFileListOut(SQLModel):
    """Paginated list response."""

    items: list[StoredFileOut]
    total: int
    page: int
    per_page: int


class UploadSessionCreate(SQLModel):
    """Body for POST /api/file-storage/uploads."""

    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(default="application/octet-stream", max_length=128)
    total_size: int = Field(gt=0)
    public: StrictBool = False


class PartOut(SQLModel):
    """One part the backend holds."""

    no: int
    etag: str
    size: int


class UploadSessionOut(SQLModel):
    """A resumable upload: what it is, and which parts the backend already has."""

    id: uuid.UUID
    filename: str
    content_type: str
    total_size: int
    part_size: int
    total_parts: int
    status: str
    public: bool
    expires_at: datetime
    parts: list[PartOut] = Field(default_factory=list)
    file: StoredFileOut | None = Field(
        default=None, description="The stored file, once the session is completed."
    )


class PartUrlsRequest(SQLModel):
    """Body for POST /uploads/{id}/part-urls."""

    parts: list[int] = Field(min_length=1, max_length=100)


class PartUrlsOut(SQLModel):
    """Where to PUT each requested part; ``direct`` is false for app-relayed parts."""

    urls: dict[int, str]
    direct: bool


class CompletePart(SQLModel):
    no: int = Field(alias="n", ge=1)
    etag: str

    model_config = ConfigDict(populate_by_name=True)  # ty: ignore[invalid-assignment]


class UploadCompleteRequest(SQLModel):
    """Body for POST /uploads/{id}/complete: the parts the client believes it sent."""

    parts: list[CompletePart] = Field(default_factory=list, max_length=10_000)
