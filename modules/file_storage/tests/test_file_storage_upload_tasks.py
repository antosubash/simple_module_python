"""The janitor and checksum tasks (``file_storage.tasks``) (#454).

Tasks run in a worker with its own sync engine, so these point
``background_tasks.sync_db`` at a throwaway SQLite file and swap in a
filesystem backend, which is all a worker needs to exercise.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from background_tasks import sync_db
from file_storage import constants, tasks
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import Base, StoredFile, UploadSession
from file_storage.settings import FileStorageSettings
from simple_module_db import all_tenants, tenant_context
from sqlalchemy import create_engine, select

TENANT = "tenant-a"


@pytest.fixture
def worker(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'worker.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    sync_db.set_database_url(url)
    backend = FilesystemBackend(root=tmp_path / "objects")
    settings = FileStorageSettings()
    monkeypatch.setattr(tasks, "_backend_and_settings", lambda: (backend, settings))
    yield backend
    sync_db.dispose_sync_engine()


def _session_row(upload_id: str, *, expires_in: timedelta, key: str | None = None):
    return UploadSession(
        tenant_id=TENANT,
        key=key or f"{TENANT}/2026/10/15/{uuid.uuid4().hex}.bin",
        filename="a.bin",
        content_type="application/octet-stream",
        total_size=10,
        part_size=constants.MIN_PART_SIZE_BYTES,
        backend_upload_id=upload_id,
        expires_at=datetime.now(UTC) + expires_in,
    )


def test_beat_schedule_runs_the_reaper_hourly():
    entry = tasks.BEAT_SCHEDULE["file-storage-reap-stale-uploads"]
    assert entry == {"task": constants.Task.REAP_STALE_UPLOADS, "schedule": 3600.0}


def test_the_reaper_aborts_only_expired_active_sessions(worker):
    expired_id = asyncio.run(worker.create_multipart("k1", "x/y"))
    live_id = asyncio.run(worker.create_multipart("k2", "x/y"))
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add_all(
            [
                _session_row(expired_id, expires_in=timedelta(hours=-1)),
                _session_row(live_id, expires_in=timedelta(hours=1)),
            ]
        )

    result = tasks.reap_stale_uploads()

    assert result == {"sessions": 1, "orphans": 0}
    assert not worker._parts_dir(expired_id).exists()
    assert worker._parts_dir(live_id).exists()
    with sync_db.sync_session() as db, all_tenants():
        statuses = {
            s.backend_upload_id: s.status for s in db.execute(select(UploadSession)).scalars()
        }
    assert statuses == {expired_id: "aborted", live_id: "active"}

    # Idempotent: nothing left to reap.
    assert tasks.reap_stale_uploads() == {"sessions": 0, "orphans": 0}


def test_a_failing_abort_is_retried_next_hour(worker, monkeypatch):
    upload_id = asyncio.run(worker.create_multipart("k", "x/y"))
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add(_session_row(upload_id, expires_in=timedelta(hours=-1)))

    async def boom(key, upload):
        raise OSError("bucket unreachable")

    monkeypatch.setattr(worker, "abort_multipart", boom)
    assert tasks.reap_stale_uploads() == {"sessions": 0, "orphans": 0}
    with sync_db.sync_session() as db, all_tenants():
        assert db.execute(select(UploadSession.status)).scalar_one() == "active"


def test_compute_checksum_fills_the_digest(worker):
    payload = b"streamed once" * 1000
    key = f"{TENANT}/2026/10/15/obj.bin"

    async def _store():
        async def _body():
            yield payload

        await worker.put(key, _body(), content_type="x/y", size=len(payload))

    asyncio.run(_store())
    file_id = uuid.uuid4()
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add(
            StoredFile(
                id=file_id,
                tenant_id=TENANT,
                key=key,
                filename="obj.bin",
                content_type="x/y",
                size_bytes=len(payload),
                backend="filesystem",
                checksum_sha256=None,
            )
        )

    digest = tasks.compute_checksum(str(file_id), TENANT)

    assert digest == hashlib.sha256(payload).hexdigest()
    with sync_db.sync_session() as db, tenant_context(TENANT):
        assert db.get(StoredFile, file_id).checksum_sha256 == digest
    # Already filled: a duplicate delivery does nothing.
    assert tasks.compute_checksum(str(file_id), TENANT) is None


def test_compute_checksum_ignores_another_tenants_file(worker):
    file_id = uuid.uuid4()
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add(
            StoredFile(
                id=file_id,
                tenant_id=TENANT,
                key="k",
                filename="a",
                content_type="x/y",
                size_bytes=1,
                backend="filesystem",
            )
        )
    assert tasks.compute_checksum(str(file_id), "tenant-b") is None


def test_the_orphan_sweep_spares_active_sessions_and_foreign_keys(worker, monkeypatch):
    own = f"{TENANT}/2026/10/15/{uuid.uuid4().hex}.bin"
    tracked_key = f"{TENANT}/2026/10/15/{uuid.uuid4().hex}.bin"
    tracked_id = asyncio.run(worker.create_multipart(tracked_key, "x/y"))
    orphan_id = asyncio.run(worker.create_multipart(own, "x/y"))
    foreign_id = asyncio.run(worker.create_multipart("another-app/exports/data.csv", "x/y"))
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add(_session_row(tracked_id, expires_in=timedelta(hours=1), key=tracked_key))

    async def stale(older_than):
        return [
            (own, orphan_id),
            (tracked_key, tracked_id),
            ("another-app/exports/data.csv", foreign_id),
        ]

    monkeypatch.setattr(worker, "list_stale_multipart", stale, raising=False)

    assert tasks.reap_stale_uploads() == {"sessions": 0, "orphans": 1}
    assert not worker._parts_dir(orphan_id).exists()
    assert worker._parts_dir(tracked_id).exists()
    assert worker._parts_dir(foreign_id).exists()


def test_compute_checksum_survives_a_deleted_object(worker):
    file_id = uuid.uuid4()
    with sync_db.sync_session() as db, tenant_context(TENANT):
        db.add(
            StoredFile(
                id=file_id,
                tenant_id=TENANT,
                key=f"{TENANT}/gone.bin",
                filename="a",
                content_type="x/y",
                size_bytes=1,
                backend="filesystem",
            )
        )
    assert tasks.compute_checksum(str(file_id), TENANT) is None
