"""Recover checksum jobs lost after the upload transaction committed (#590)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from background_tasks import sync_db
from file_storage import constants, tasks
from file_storage.models import Base, StoredFile
from simple_module_db import tenant_context
from simple_module_db.tenancy import current_tenant_id
from sqlalchemy import create_engine


@pytest.fixture
def checksum_worker(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'checksums.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(sync_db, "discover_audit_callback", lambda: None)
    sync_db.set_database_url(url, tenant_strict=True)
    yield
    sync_db.dispose_sync_engine()


def _file(tenant, *, age=60, checksum=None, deleted=False):
    return StoredFile(
        tenant_id=tenant,
        key=f"{tenant}/{age}/{deleted}/{checksum}",
        filename="file.bin",
        content_type="application/octet-stream",
        size_bytes=1,
        backend=constants.BackendId.FILESYSTEM,
        created_at=datetime.now(UTC) - timedelta(minutes=age),
        checksum_sha256=checksum,
        is_deleted=deleted,
    )


def test_reconciler_is_registered_hourly():
    assert tasks.BEAT_SCHEDULE["file-storage-reconcile-checksums"] == {
        "task": "file_storage.reconcile_checksums",
        "schedule": 3600.0,
    }
    assert tasks.reconcile_checksums.name == "file_storage.reconcile_checksums"


def test_recovers_lost_jobs_across_tenants_and_skips_ineligible_files(
    checksum_worker,
    monkeypatch,
):
    rows = [_file("tenant-a"), _file("tenant-b")]
    with sync_db.sync_session() as db:
        for row in [
            *rows,
            _file("tenant-a", age=0),
            _file("tenant-a", checksum="a" * 64),
            _file("tenant-a", deleted=True),
        ]:
            with tenant_context(row.tenant_id):
                db.add(row)
                db.flush()

    published = []

    def publish(*, args, **kwargs):
        published.append((args, current_tenant_id.get()))

    monkeypatch.setattr(tasks.compute_checksum, "apply_async", publish)
    assert tasks.reconcile_checksums() == 2
    assert published == [((str(row.id), row.tenant_id), row.tenant_id) for row in rows]


def test_batch_is_bounded_and_failed_publishes_are_retried(checksum_worker, monkeypatch):
    with sync_db.sync_session() as db, tenant_context("tenant-a"):
        db.add_all([_file("tenant-a", age=60), _file("tenant-a", age=90)])
    monkeypatch.setattr(constants, "CHECKSUM_RECONCILE_BATCH_SIZE", 1)
    publish = Mock(side_effect=OSError("broker unavailable"))
    monkeypatch.setattr(tasks.compute_checksum, "apply_async", publish)

    assert tasks.reconcile_checksums() == 1
    assert publish.call_count == 1
    lost_args = publish.call_args.kwargs["args"]
    publish.reset_mock(side_effect=True)
    assert tasks.reconcile_checksums() == 1
    assert publish.call_args.kwargs["args"] == lost_args
