"""Public synchronous worker file operations (#708)."""

import hashlib
import stat
from io import BytesIO
from uuid import uuid4

import pytest
from background_tasks import outbox_worker
from file_storage import contracts
from file_storage.backend_guard import BackendUnavailableError
from file_storage.contracts import FileUploaded, NotSupportedError, StoredFileOut
from file_storage.models import StoredFile
from file_storage.service import (
    ContentTypeNotAllowedError,
    FileTooLargeError,
    StoredFileNotFoundError,
)
from file_storage.upload_support import QuotaExceededError
from file_storage_worker_helpers import set_setting
from simple_module_db import tenant_context
from simple_module_db.tenancy import TenantIsolationError
from sqlalchemy import select
from sqlalchemy.orm import Session


def test_contract_exports_worker_functions():
    for name in ("store_path", "open_local", "presigned_url"):
        assert callable(getattr(contracts, name, None)), name


def test_path_roundtrip_and_after_commit_event(worker_db, tmp_path):
    _root, engine, bus = worker_db
    source = tmp_path / "input.tif"
    source.write_bytes(b"raster")
    received = []

    async def uploaded(event):
        # A separate connection sees only committed metadata.
        with Session(engine) as db:
            assert db.get(StoredFile, event.file_id) is not None
        received.append(event)

    bus.subscribe(FileUploaded, uploaded)
    with tenant_context("alpha"):
        out = contracts.store_path(source, content_type="image/tiff", public=True)
        assert isinstance(out, StoredFileOut)
        assert (out.filename, out.content_type, out.size_bytes, out.public) == (
            "input.tif",
            "image/tiff",
            6,
            True,
        )
        assert out.key.startswith("alpha/")
        assert out.checksum_sha256 == hashlib.sha256(b"raster").hexdigest()
        with contracts.open_local(out.id) as path:
            assert path.read_bytes() == b"raster"
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert not path.parent.exists()
    assert len(received) == 1
    assert (received[0].file_id, received[0].key, received[0].size_bytes) == (out.id, out.key, 6)


def test_stream_current_position_and_ownership(worker_db):
    stream = BytesIO(b"skipcontents")
    stream.seek(4)
    with tenant_context("alpha"):
        out = contracts.store_path(stream, filename="output.bin")
        assert out.size_bytes == 8
        with contracts.open_local(out.id) as path:
            assert path.read_bytes() == b"contents"
    assert not stream.closed
    assert stream.tell() == 12


def test_anonymous_stream_needs_filename(worker_db):
    stream = BytesIO(b"unchanged")
    with tenant_context("alpha"), pytest.raises(ValueError, match="filename"):
        contracts.store_path(stream)
    assert stream.tell() == 0 and not stream.closed


def test_unscoped_upload_fails_before_opening_source(worker_db, tmp_path):
    with pytest.raises(TenantIsolationError):
        contracts.store_path(tmp_path / "does-not-exist")
    assert not worker_db[0].exists()


@pytest.mark.parametrize("operation", ["open_local", "presigned_url"])
def test_missing_and_cross_tenant_ids(worker_db, operation):
    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"private"), filename="a.bin")
    for target in (out.id, uuid4()):
        with tenant_context("beta"), pytest.raises(StoredFileNotFoundError):
            if operation == "open_local":
                with contracts.open_local(target):
                    pass
            else:
                contracts.presigned_url(target)


@pytest.mark.parametrize(
    "name,value,content_type,error",
    [
        ("max_file_size_bytes", "2", "text/plain", FileTooLargeError),
        ("allowed_content_types", '["image/png"]', "text/plain", ContentTypeNotAllowedError),
        ("quota_bytes", "2", "text/plain", QuotaExceededError),
    ],
)
def test_upload_limits_leave_no_objects_or_rows(worker_db, name, value, content_type, error):
    root, engine, _ = worker_db
    set_setting(engine, name, value, "json" if name == "allowed_content_types" else "integer")
    with tenant_context("alpha"), pytest.raises(error):
        contracts.store_path(BytesIO(b"too large"), filename="a.txt", content_type=content_type)
    assert not list(root.rglob("*.*"))
    with Session(engine) as db:
        assert list(db.scalars(select(StoredFile))) == []


@pytest.mark.parametrize("phase", ["flush", "commit"])
def test_database_failure_compensates(worker_db, monkeypatch, phase):
    root, engine, bus = worker_db
    received = []

    async def uploaded(event):
        received.append(event)

    bus.subscribe(FileUploaded, uploaded)
    factory = outbox_worker.worker_session_factory()

    async def fail(*args, **kwargs):
        raise RuntimeError("database failed")

    monkeypatch.setattr(factory.class_, phase, fail)
    with tenant_context("alpha"), pytest.raises(RuntimeError, match="database failed"):
        contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    assert not list(root.rglob("*.bin"))
    with Session(engine) as db:
        assert list(db.scalars(select(StoredFile))) == []
    assert received == []


def test_local_context_cleans_on_body_failure(worker_db):
    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"contents"), filename="a.bin")
        with pytest.raises(RuntimeError, match="consumer"), contracts.open_local(out.id) as path:
            raise RuntimeError("consumer")
        assert not path.parent.exists()


def test_filesystem_presign_is_unsupported(worker_db):
    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(), filename="empty")
        with pytest.raises(NotSupportedError):
            contracts.presigned_url(out.id)


@pytest.mark.parametrize("operation", ["open_local", "presigned_url"])
def test_read_refuses_wrong_backend(worker_db, operation):
    with tenant_context("alpha"):
        out = contracts.store_path(BytesIO(b"contents"), filename="a.bin")
    with Session(worker_db[1]) as db:
        row = db.get(StoredFile, out.id)
        row.backend = "other"
        db.commit()
    with tenant_context("alpha"), pytest.raises(BackendUnavailableError):
        if operation == "open_local":
            with contracts.open_local(out.id):
                pass
        else:
            contracts.presigned_url(out.id)


def test_worker_context_does_not_leak_between_calls(worker_db):
    with tenant_context("alpha"):
        a = contracts.store_path(BytesIO(b"a"), filename="a.bin")
        factory = outbox_worker.worker_session_factory()
    with tenant_context("beta"):
        b = contracts.store_path(BytesIO(b"b"), filename="b.bin")
        assert factory is outbox_worker.worker_session_factory()
        with pytest.raises(StoredFileNotFoundError), contracts.open_local(a.id):
            pass
    with pytest.raises(TenantIsolationError):
        contracts.store_path(BytesIO(b"c"), filename="c.bin")
    assert a.key.startswith("alpha/") and b.key.startswith("beta/")


def test_concurrent_callers_keep_tenants_and_pools_separate(worker_db):
    from concurrent.futures import ThreadPoolExecutor

    def store(tenant):
        with tenant_context(tenant):
            out = contracts.store_path(BytesIO(tenant.encode()), filename="result.bin")
            return out, id(outbox_worker.worker_session_factory())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store, ["alpha", "beta"]))
    assert [out.key.split("/")[0] for out, _ in results] == ["alpha", "beta"]
    assert len({pool for _, pool in results}) == 2


def test_contract_import_does_not_load_worker_dependencies():
    import subprocess
    import sys

    code = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "background_tasks" or name.startswith("background_tasks."):
        raise AssertionError("contracts imported worker dependencies eagerly")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from file_storage.contracts import store_path, open_local, presigned_url
assert all(callable(fn) for fn in (store_path, open_local, presigned_url))
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=20)
