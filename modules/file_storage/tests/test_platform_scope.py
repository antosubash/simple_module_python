"""``platform=True`` lifts isolation for the platform row only (#383).

``platform_scope`` is an ``all_tenants()`` block, and a flush inside it flushes
the whole session. The caller's unrelated pending writes must therefore be
flushed *before* the bypass — stamped with, and checked against, the bound
tenant — never carried through it.
"""

from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from fastapi import UploadFile
from file_storage import constants
from file_storage.models import StoredFile
from file_storage.service import FileStorageService
from simple_module_db import (
    DEFAULT_TENANT_ID,
    PLATFORM_TENANT_ID,
    TenantIsolationError,
    all_tenants,
    is_valid_tenant_id,
    tenant_context,
)
from sqlalchemy import select


def _row(**extra) -> StoredFile:
    return StoredFile(
        key=f"pending/{uuid.uuid4().hex}.txt",
        filename="pending.txt",
        content_type="text/plain",
        size_bytes=1,
        backend=constants.BackendId.FILESYSTEM,
        checksum_sha256="0" * 64,
        **extra,
    )


def _service(app, session) -> FileStorageService:
    services = app.state.file_storage
    return FileStorageService(session, services.backend, services.settings)


def _logo() -> UploadFile:
    return UploadFile(BytesIO(b"\x89PNG\r\n\x1a\n"), filename="logo.png")


def test_the_platform_owner_is_reserved_and_distinct():
    assert PLATFORM_TENANT_ID != DEFAULT_TENANT_ID
    assert not is_valid_tenant_id(PLATFORM_TENANT_ID)
    with pytest.raises(ValueError), tenant_context(PLATFORM_TENANT_ID):
        pass


async def test_a_pending_tenant_row_is_stamped_with_the_bound_tenant(app):
    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            pending = _row()
            session.add(pending)
            platform = await _service(app, session).upload(_logo(), platform=True)
            await session.commit()

    async with app.state.sm.db.session_factory() as session:
        with all_tenants():
            rows = await session.execute(select(StoredFile.id, StoredFile.tenant_id))
        owners = dict(rows.all())
    assert owners == {pending.id: "acme", platform.id: PLATFORM_TENANT_ID}


async def test_the_pending_rows_audit_entry_keeps_the_bound_tenant(app):
    from audit_log.models import AuditEntry

    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            pending = _row()
            session.add(pending)
            await _service(app, session).upload(_logo(), platform=True)
            await session.commit()

    async with app.state.sm.db.session_factory() as session:
        tenants = (
            await session.execute(
                select(AuditEntry.tenant_id).where(AuditEntry.entity_id == str(pending.id))
            )
        ).scalars()
        assert list(tenants) == ["acme"]


async def test_a_pending_cross_tenant_write_is_still_refused(app):
    """Before the fix the platform flush ran it under ``all_tenants()``."""
    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            session.add(_row(tenant_id="globex"))
            with pytest.raises(TenantIsolationError):
                await _service(app, session).upload(_logo(), platform=True)


async def test_a_platform_read_does_not_autoflush_pending_writes_unguarded(app):
    async with app.state.sm.db.session_factory() as session:
        with tenant_context("acme"):
            session.add(_row(tenant_id="globex"))
            with pytest.raises(TenantIsolationError):
                await _service(app, session).get(uuid.uuid4(), platform=True)
