"""Tenant teardown preserves a retryable manifest after deleting source rows."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from background_tasks.constants import OutboxStatus
from background_tasks.models import OutboxMessage
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from background_tasks.outbox_transport import WorkerOutboxTransport
from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import StoredFile, UploadSession
from file_storage.tenant_deletion import register_tenant_deletion
from file_storage.thumbnails import variant_key
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db import all_tenants, tenant_context
from sqlmodel import select


async def test_tenant_cleanup_commits_manifest_and_retries(app, tmp_path, monkeypatch):
    bus = EventBus()
    transport = WorkerOutboxTransport()
    monkeypatch.setattr(transport, "schedule", lambda db, ids: None)
    bus.durable_transport = transport
    settings = app.state.file_storage.settings.model_copy(update={"fs_root_path": str(tmp_path)})
    backend = FilesystemBackend(tmp_path)
    monkeypatch.setattr("file_storage.tenant_deletion.build_backend", lambda settings: backend)
    register_tenant_deletion(
        bus, SimpleNamespace(state=SimpleNamespace(file_storage=SimpleNamespace(settings=settings)))
    )
    tenant_id = "deleted-storage-tenant"
    key = f"{tenant_id}/original.txt"
    variant = variant_key(key, constants.THUMBNAIL_WIDTHS[0])

    async def body():
        yield b"bytes"

    for target in (key, variant):
        await backend.put(target, body(), content_type="text/plain", size=5)
    upload_id = await backend.create_multipart(f"{tenant_id}/partial", "text/plain")
    factory = app.state.sm.db.session_factory
    with tenant_context(tenant_id):
        async with factory() as db:
            db.add(
                StoredFile(
                    tenant_id=tenant_id,
                    key=key,
                    filename="original.txt",
                    content_type="text/plain",
                    size_bytes=5,
                    backend=constants.BackendId.FILESYSTEM,
                    public=True,
                    is_deleted=True,
                )
            )
            db.add(
                UploadSession(
                    tenant_id=tenant_id,
                    key=f"{tenant_id}/partial",
                    filename="partial",
                    content_type="text/plain",
                    total_size=5,
                    part_size=5,
                    backend_upload_id=upload_id,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
            await bus.publish_durable(TenantDeleted(tenant_id, "deleted", "Deleted"), db)
            await db.commit()
    with tenant_context("retained-storage-tenant"):
        async with factory() as db:
            db.add(
                StoredFile(
                    key="retained-storage-tenant/keep.txt",
                    filename="keep.txt",
                    content_type="text/plain",
                    size_bytes=5,
                    backend=constants.BackendId.FILESYSTEM,
                )
            )
            await db.commit()
    policy = OutboxPolicy(max_attempts=8, lease_seconds=300)
    assert (await dispatch(factory, bus, policy, limit=1)).delivered == 1
    assert await backend.exists(key)
    with all_tenants():
        async with factory() as db:
            remaining = (
                (await db.execute(select(StoredFile).execution_options(include_deleted=True)))
                .scalars()
                .all()
            )
            assert [row.tenant_id for row in remaining] == ["retained-storage-tenant"]
            assert not (await db.execute(select(UploadSession))).scalars().all()
    original_delete = backend.delete
    monkeypatch.setattr(backend, "delete", AsyncMock(side_effect=RuntimeError("offline")))
    assert (await dispatch(factory, bus, policy)).retrying == 2
    async with factory() as db:
        rows = (await db.execute(select(OutboxMessage))).scalars().all()
        assert sum(row.status == OutboxStatus.PENDING for row in rows) == 2
    monkeypatch.setattr(backend, "delete", original_delete)
    assert (
        await dispatch(factory, bus, policy, now=datetime.now(UTC) + timedelta(minutes=1))
    ).delivered == 2
    assert not await backend.exists(key)
    assert not await backend.exists(variant)
    assert not backend._parts_dir(upload_id).exists()
    assert (await dispatch(factory, bus, policy)).delivered == 0


@pytest.mark.parametrize("rollback", [False, True])
async def test_inline_cleanup_defers_objects_until_commit(
    db_session, tmp_path, monkeypatch, rollback
):
    from simple_module_db.transaction import finalize_session, rollback_session
    from tenants.models import Tenant
    from tenants.service import TenantService

    bus = EventBus()
    backend = FilesystemBackend(tmp_path)
    from file_storage.settings import FileStorageSettings

    settings = FileStorageSettings()
    monkeypatch.setattr("file_storage.tenant_deletion.build_backend", lambda settings: backend)
    register_tenant_deletion(
        bus, SimpleNamespace(state=SimpleNamespace(file_storage=SimpleNamespace(settings=settings)))
    )
    tenant_id = "inline-storage"
    key = f"{tenant_id}/original.txt"
    variant = variant_key(key, constants.THUMBNAIL_WIDTHS[0])

    async def body():
        yield b"bytes"

    for target in (key, variant):
        await backend.put(target, body(), content_type="text/plain", size=5)
    upload_key = f"{tenant_id}/partial"
    upload_id = await backend.create_multipart(upload_key, "text/plain")
    db_session.add(Tenant(id=tenant_id, slug=tenant_id, name=tenant_id))
    with tenant_context(tenant_id):
        db_session.add(
            StoredFile(
                key=key,
                filename="original.txt",
                content_type="text/plain",
                size_bytes=5,
                backend=constants.BackendId.FILESYSTEM,
                is_deleted=True,
            )
        )
        db_session.add(
            UploadSession(
                key=upload_key,
                filename="partial",
                content_type="text/plain",
                total_size=5,
                part_size=5,
                backend_upload_id=upload_id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await finalize_session(db_session)
        await TenantService(db_session, bus=bus).delete_tenant(tenant_id)
        for model in (StoredFile, UploadSession):
            assert (
                not (
                    await db_session.execute(select(model).execution_options(include_deleted=True))
                )
                .scalars()
                .all()
            )
        assert await backend.exists(key)
        assert await backend.exists(variant)
        assert backend._parts_dir(upload_id).exists()
        if rollback:
            await rollback_session(db_session)
        else:
            await finalize_session(db_session)
        assert await backend.exists(key) == rollback
        assert await backend.exists(variant) == rollback
        assert backend._parts_dir(upload_id).exists() == rollback
        for model in (StoredFile, UploadSession):
            rows = (
                (await db_session.execute(select(model).execution_options(include_deleted=True)))
                .scalars()
                .all()
            )
            assert len(rows) == int(rollback)
