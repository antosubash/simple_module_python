"""Worker download, event and compensation failure boundaries (#708)."""

import asyncio
from concurrent.futures import CancelledError
from io import BytesIO

import pytest
from background_tasks import outbox_worker
from file_storage import contracts
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import StoredFile
from file_storage_worker_helpers import set_setting
from simple_module_db import tenant_context
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_cancelled_flush_removes_uploaded_bytes(worker_db, monkeypatch):
    factory = outbox_worker.worker_session_factory()

    async def fail(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(factory.class_, "flush", fail)
    with tenant_context("alpha"), pytest.raises(CancelledError):
        contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    assert not list(worker_db[0].rglob("*.bin"))


def test_failed_compensation_preserves_commit_error(worker_db, monkeypatch):
    factory = outbox_worker.worker_session_factory()

    async def commit(*args, **kwargs):
        raise ValueError("commit failed")

    async def delete(*args, **kwargs):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(factory.class_, "commit", commit)
    monkeypatch.setattr(FilesystemBackend, "delete", delete)
    with tenant_context("alpha"), pytest.raises(ValueError, match="commit failed"):
        contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    with Session(worker_db[1]) as db:
        assert list(db.scalars(select(StoredFile))) == []


def test_download_failure_closes_stream_and_removes_temporary_directory(worker_db, monkeypatch):
    from tempfile import TemporaryDirectory

    from file_storage import worker

    directories = []
    closed = []

    def temporary(**kwargs):
        directory = TemporaryDirectory(**kwargs)
        directories.append(directory.name)
        return directory

    async def get(self, key):
        async def broken():
            try:
                yield b"partial"
                raise ValueError("download failed")
            finally:
                closed.append(True)

        return broken()

    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"contents"), filename="a.bin")
        monkeypatch.setattr(FilesystemBackend, "get", get)
        monkeypatch.setattr(worker, "TemporaryDirectory", temporary)
        with pytest.raises(ValueError, match="download failed"), contracts.open_local(out.id):
            pytest.fail("partial download was yielded")
    from pathlib import Path

    assert directories and not Path(directories[0]).exists()
    assert closed == [True]


def test_presign_honors_settings_override_and_download_headers(worker_db, monkeypatch):
    seen = []

    async def sign(self, key, ttl_seconds, **kwargs):
        seen.append((key, ttl_seconds, kwargs))
        return "https://bucket.example/signed"

    monkeypatch.setattr(FilesystemBackend, "supports_presigned_url", True)
    monkeypatch.setattr(FilesystemBackend, "presigned_get_url", sign)
    set_setting(worker_db[1], "s3_presign_ttl_seconds", "42")
    with tenant_context("alpha"):
        out = contracts.store_path(
            BytesIO(b"contents"), filename="report.tif", content_type="image/tiff"
        )
        assert contracts.presigned_url(out.id) == "https://bucket.example/signed"
        assert contracts.presigned_url(out.id, ttl_seconds=12) == "https://bucket.example/signed"
        with pytest.raises(ValueError, match="positive"):
            contracts.presigned_url(out.id, ttl_seconds=0)
    assert [ttl for _, ttl, _ in seen] == [42, 12]
    assert all(key == out.key for key, _, _ in seen)
    assert seen[0][2] == {
        "content_type": "image/tiff",
        "content_disposition": "attachment; filename=\"report.tif\"; filename*=UTF-8''report.tif",
    }


def test_named_handle_infers_basename_and_stays_open(worker_db, tmp_path):
    source = tmp_path / "named.bin"
    source.write_bytes(b"named")
    with source.open("rb") as handle, tenant_context("alpha"):
        out = contracts.store_path(handle)
        assert out.filename == "named.bin"
        assert not handle.closed


@pytest.mark.parametrize("operation", ["open_local", "presigned_url"])
def test_unscoped_reads_fail_closed(worker_db, operation):
    from simple_module_db.tenancy import TenantIsolationError

    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"private"), filename="a.bin")
    with pytest.raises(TenantIsolationError):
        if operation == "open_local":
            with contracts.open_local(out.id):
                pytest.fail("unscoped file was exposed")
        else:
            contracts.presigned_url(out.id)


def test_download_does_not_hold_metadata_connection(worker_db, monkeypatch):
    factory = outbox_worker.worker_session_factory()
    real = FilesystemBackend.get
    checked_out = []

    async def get(self, key):
        checked_out.append(factory.kw["bind"].pool.checkedout())
        return await real(self, key)

    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"contents"), filename="a.bin")
        monkeypatch.setattr(FilesystemBackend, "get", get)
        with contracts.open_local(out.id) as path:
            assert path.read_bytes() == b"contents"
    assert checked_out == [0]


def test_commit_acknowledgement_failure_keeps_committed_object(worker_db, monkeypatch):
    factory = outbox_worker.worker_session_factory()
    real_commit = factory.class_.commit

    async def commit_then_cancel(db):
        await real_commit(db)
        raise asyncio.CancelledError()

    monkeypatch.setattr(factory.class_, "commit", commit_then_cancel)
    with tenant_context("alpha"), pytest.raises(CancelledError):
        contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    with Session(worker_db[1]) as db:
        row = db.scalars(select(StoredFile)).one()
    assert (worker_db[0] / row.key[:2] / row.key).read_bytes() == b"contents"


def test_unverifiable_commit_outcome_preserves_object_and_original_error(worker_db, monkeypatch):
    factory = outbox_worker.worker_session_factory()

    async def commit(*args):
        raise ValueError("commit failed")

    async def get(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(factory.class_, "commit", commit)
    monkeypatch.setattr(factory.class_, "get", get)
    with tenant_context("alpha"), pytest.raises(ValueError, match="commit failed"):
        contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    objects = list(worker_db[0].rglob("*.bin"))
    assert len(objects) == 1 and objects[0].read_bytes() == b"contents"
