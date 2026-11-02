"""SQLModel tables for the file_storage module."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, MultiTenantMixin, SoftDeleteMixin
from simple_module_db.types import AwareDateTime
from sqlalchemy import Index
from sqlmodel import Field

from file_storage import constants

Base = create_module_base(constants.MODULE_NAME)


class StoredFile(Base, AuditMixin, SoftDeleteMixin, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    """A file persisted to a configured storage backend.

    The ``backend`` column records which provider holds the bytes — important
    if the active backend is changed after ingest: object access is refused
    until the bytes and row are manually migrated. This records provider type,
    not a historical bucket/root configuration.

    Tenant-scoped (#383): every read, update and delete is filtered to the
    bound tenant, so a file id from another tenant simply does not resolve.
    ``key`` is unique per tenant — new keys start with ``{tenant_id}/`` so the
    backend namespaces are disjoint too, while rows written before adoption
    keep the un-prefixed key they were stored under (the column holds the full
    object path; nothing derives it).
    """

    __tablename__ = constants.TABLE_STORED_FILE

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key: str = Field(max_length=512)
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=128)
    # BIGINT: server-side puts can exceed 2 GiB (#708).
    size_bytes: int = Field(sa_column=sa.Column(sa.BigInteger(), nullable=False))
    backend: str = Field(max_length=32)
    # Null for multipart uploads until ``file_storage.compute_checksum`` has
    # streamed the object (or forever, with no background_tasks): the bytes
    # never pass through the app, so there is nothing to hash on the way in.
    checksum_sha256: str | None = Field(default=None, max_length=64)
    # Opt-in anonymous serving (#353): only ``public`` rows are reachable from
    # ``GET {prefix}/public/{id}``. ``sa.false()`` renders as ``0`` on SQLite and
    # ``false`` on Postgres, which a literal ``text("0")`` default would not.
    public: bool = Field(
        default=False,
        sa_column=sa.Column(sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    extra_metadata: dict = Field(
        default_factory=dict,
        sa_type=sa.JSON,
    )

    __table_args__ = (
        Index(f"ix_{constants.TABLE_STORED_FILE}_tenant_key", "tenant_id", "key", unique=True),
        Index(f"ix_{constants.TABLE_STORED_FILE}_created_by", "created_by"),
        Index(f"ix_{constants.TABLE_STORED_FILE}_is_deleted", "is_deleted"),
    )


class UploadSession(Base, AuditMixin, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    """A resumable, multipart upload in progress (#454).

    ``created_by`` is the owner: only they can resume, finish or abort it. The
    backend's own part listing — not this row — says which parts have arrived,
    so a lost response or a second tab can never disagree with the bucket.
    """

    __tablename__ = constants.TABLE_UPLOAD_SESSION

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key: str = Field(max_length=512)
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=128)
    total_size: int = Field(sa_column=sa.Column(sa.BigInteger(), nullable=False))
    part_size: int = Field(sa_column=sa.Column(sa.BigInteger(), nullable=False))
    backend_upload_id: str = Field(max_length=255)
    status: str = Field(default=constants.UploadStatus.ACTIVE, max_length=16)
    public: bool = Field(
        default=False,
        sa_column=sa.Column(sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    expires_at: datetime = Field(sa_column=sa.Column(AwareDateTime(), nullable=False))
    # Set on completion, so a retried ``complete`` answers with the same file.
    file_id: uuid.UUID | None = Field(default=None, sa_column=sa.Column(sa.Uuid(), nullable=True))

    __table_args__ = (
        Index(f"ix_{constants.TABLE_UPLOAD_SESSION}_tenant_key", "tenant_id", "key", unique=True),
        Index(f"ix_{constants.TABLE_UPLOAD_SESSION}_status_expires", "status", "expires_at"),
        Index(f"ix_{constants.TABLE_UPLOAD_SESSION}_created_by", "created_by"),
    )
