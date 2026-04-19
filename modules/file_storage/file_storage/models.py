"""SQLModel tables for the file_storage module."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin, SoftDeleteMixin
from sqlalchemy import Index
from sqlmodel import Field

from file_storage import constants

# PostgreSQL → ``file_storage`` schema; SQLite → table name is prefixed below.
Base = create_module_base(constants.MODULE_NAME)


class StoredFile(Base, AuditMixin, SoftDeleteMixin, table=True):  # ty: ignore[unsupported-base]
    """A file persisted to a configured storage backend.

    The ``backend`` column records which provider holds the bytes — important
    if the active backend is changed after ingest, since old rows still need
    to be located on their original provider until they're migrated.
    """

    __tablename__ = constants.TABLE_STORED_FILE

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key: str = Field(max_length=512)
    filename: str = Field(max_length=255)
    content_type: str = Field(max_length=128)
    size_bytes: int = Field()
    backend: str = Field(max_length=32)
    checksum_sha256: str = Field(max_length=64)
    extra_metadata: dict = Field(
        default_factory=dict,
        sa_type=sa.JSON,
    )

    __table_args__ = (
        Index(f"ix_{constants.TABLE_STORED_FILE}_key", "key", unique=True),
        Index(f"ix_{constants.TABLE_STORED_FILE}_created_by", "created_by"),
        Index(f"ix_{constants.TABLE_STORED_FILE}_is_deleted", "is_deleted"),
    )
