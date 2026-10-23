"""Tenant cleanup manifests bound both file and upload payloads."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from file_storage import constants
from file_storage.models import StoredFile, UploadSession
from file_storage.tenant_deletion import register_tenant_deletion
from simple_module_core.events import EventBus
from simple_module_core.tenant_events import TenantDeleted
from simple_module_db import tenant_context
from simple_module_db.transaction import finalize_session


async def test_cleanup_chunks_preserve_every_entry(db_session, monkeypatch):
    monkeypatch.setattr("file_storage.tenant_deletion.CLEANUP_BATCH_SIZE", 2)
    bus = EventBus()
    register_tenant_deletion(bus, None)
    with tenant_context("chunked"):
        for i in range(5):
            db_session.add(
                StoredFile(
                    key=f"file-{i}",
                    filename="file",
                    content_type="text/plain",
                    size_bytes=1,
                    backend=constants.BackendId.FILESYSTEM,
                )
            )
            db_session.add(
                UploadSession(
                    key=f"upload-{i}",
                    filename="upload",
                    content_type="text/plain",
                    total_size=1,
                    part_size=1,
                    backend_upload_id=f"id-{i}",
                    expires_at=datetime.now(UTC),
                )
            )
        await finalize_session(db_session)
        await bus.publish_durable_or_inline(
            TenantDeleted("chunked", "chunked", "Chunked"), db_session
        )
        publish = AsyncMock()
        monkeypatch.setattr(bus, "publish_durable_or_inline", publish)
        assert publish.await_count == 0
        await finalize_session(db_session)
    manifests = [call.args[0] for call in publish.await_args_list]
    assert len(manifests) == 6
    assert all(0 < len(m.files) + len(m.uploads) <= 2 for m in manifests)
    assert {key for m in manifests for _, key in m.files} == {f"file-{i}" for i in range(5)}
    assert {entry for m in manifests for entry in m.uploads} == {
        (f"upload-{i}", f"id-{i}") for i in range(5)
    }
