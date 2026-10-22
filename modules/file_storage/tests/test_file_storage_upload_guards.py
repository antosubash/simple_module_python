"""Direct unit tests for ``upload_guards.UploadGuards`` (#454), without the HTTP layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from file_storage import constants
from file_storage import upload_guards as guards_module
from file_storage.contracts.service import StorageError
from file_storage.models import StoredFile, UploadSession
from file_storage.upload_guards import UploadGuards
from file_storage.upload_support import DirectUploadUnsupportedError, QuotaExceededError
from simple_module_db import tenant_context
from sqlalchemy import select

OWNER = "user-1"
OTHER = "user-2"


class _Backend:
    backend_id = "fake"
    supports_direct_upload = True

    def __init__(self) -> None:
        self.aborted: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        self.fail = False

    async def abort_multipart(self, key: str, upload_id: str) -> None:
        if self.fail:
            raise StorageError("boom")
        self.aborted.append((key, upload_id))

    async def delete(self, key: str) -> None:
        if self.fail:
            raise StorageError("boom")
        self.deleted.append(key)


class _Guards(UploadGuards):
    def __init__(self, db: Any, backend: Any, **settings: Any) -> None:
        self.db = db
        self.files = SimpleNamespace(backend=backend)
        defaults = {"quota_bytes": None, "upload_session_retention_days": 7}
        self.settings = SimpleNamespace(**{**defaults, **settings})


@pytest.fixture
def backend() -> _Backend:
    return _Backend()


def _session(
    *,
    status: str = constants.UploadStatus.ACTIVE,
    total: int = 100,
    expires_in: timedelta = timedelta(hours=1),
    owner: str = OWNER,
) -> UploadSession:
    return UploadSession(
        key=f"t1/{uuid.uuid4()}.bin",
        filename="f.bin",
        content_type="application/octet-stream",
        total_size=total,
        part_size=10,
        backend_upload_id="up-1",
        status=status,
        expires_at=datetime.now(UTC) + expires_in,
        created_by=owner,
    )


def _stored(size: int) -> StoredFile:
    return StoredFile(
        key=f"t1/{uuid.uuid4()}.bin",
        filename="s.bin",
        content_type="application/octet-stream",
        size_bytes=size,
        backend="fake",
    )


class TestBackendProperty:
    def test_returns_a_direct_upload_capable_backend(self, backend):
        assert _Guards(None, backend).backend is backend

    def test_refuses_a_backend_without_direct_upload(self):
        plain = SimpleNamespace(backend_id="local")
        with pytest.raises(DirectUploadUnsupportedError, match="local"):
            _Guards(None, plain).backend  # noqa: B018

    def test_refuses_a_backend_that_declares_it_unsupported(self):
        off = SimpleNamespace(backend_id="local", supports_direct_upload=False)
        with pytest.raises(DirectUploadUnsupportedError):
            _Guards(None, off).backend  # noqa: B018


class TestCleanupHelpers:
    async def test_abort_backend_forwards_the_upload_id(self, backend):
        await _Guards(None, backend)._abort_backend("k", "u")
        assert backend.aborted == [("k", "u")]

    async def test_abort_backend_swallows_storage_errors(self, backend, caplog):
        backend.fail = True
        await _Guards(None, backend)._abort_backend("k", "u")
        assert "file_storage.abort_failed" in caplog.text

    async def test_drop_object_deletes_and_swallows_storage_errors(self, backend, caplog):
        guards = _Guards(None, backend)
        await guards._drop_object("k")
        assert backend.deleted == ["k"]
        backend.fail = True
        await guards._drop_object("k2")
        assert "file_storage.cleanup_failed" in caplog.text

    async def test_reject_drops_the_object_and_aborts_the_session(self, backend, db_session):
        with tenant_context("t1"):
            row = _session()
            db_session.add(row)
            await db_session.flush()
            await _Guards(db_session, backend)._reject(row)
        assert backend.deleted == [row.key]
        assert row.status == constants.UploadStatus.ABORTED

    async def test_reject_still_aborts_when_the_object_cannot_be_deleted(self, backend, db_session):
        backend.fail = True
        with tenant_context("t1"):
            row = _session()
            db_session.add(row)
            await db_session.flush()
            await _Guards(db_session, backend)._reject(row)
        assert row.status == constants.UploadStatus.ABORTED


class TestPurgeFinished:
    @pytest.mark.parametrize("owner", [None, ""])
    async def test_without_an_owner_nothing_is_deleted(self, backend, db_session, owner):
        assert await _Guards(db_session, backend).purge_finished(owner=owner) == 0

    async def test_deletes_only_this_owners_finished_rows_past_retention(self, backend, db_session):
        old = -timedelta(days=30)
        with tenant_context("t1"):
            doomed = [
                _session(status=constants.UploadStatus.COMPLETED, expires_in=old),
                _session(status=constants.UploadStatus.ABORTED, expires_in=old),
            ]
            kept = [
                _session(expires_in=old),  # still ACTIVE, however stale
                _session(status=constants.UploadStatus.COMPLETED, expires_in=-timedelta(days=1)),
                _session(status=constants.UploadStatus.COMPLETED, expires_in=old, owner=OTHER),
            ]
            db_session.add_all([*doomed, *kept])
            await db_session.flush()

            removed = await _Guards(db_session, backend).purge_finished(owner=OWNER)

            remaining = set((await db_session.scalars(select(UploadSession.id))).all())
        assert removed == 2
        assert remaining == {row.id for row in kept}

    async def test_zero_day_retention_purges_anything_already_expired(self, backend, db_session):
        with tenant_context("t1"):
            db_session.add(
                _session(status=constants.UploadStatus.COMPLETED, expires_in=-timedelta(seconds=5))
            )
            await db_session.flush()
            removed = await _Guards(
                db_session, backend, upload_session_retention_days=0
            ).purge_finished(owner=OWNER)
        assert removed == 1


class TestCheckQuota:
    async def test_no_quota_never_refuses(self, backend, db_session):
        with tenant_context("t1"):
            await _Guards(db_session, backend)._check_quota(10**15, reserve=True)

    async def test_refuses_stored_bytes_plus_the_new_size_past_the_quota(self, backend, db_session):
        with tenant_context("t1"):
            db_session.add(_stored(60))
            await db_session.flush()
            guards = _Guards(db_session, backend, quota_bytes=100)
            await guards._check_quota(40, reserve=False)  # exactly at the limit
            with pytest.raises(QuotaExceededError, match="100"):
                await guards._check_quota(41, reserve=False)

    async def test_open_sessions_only_count_when_reserving(self, backend, db_session):
        with tenant_context("t1"):
            db_session.add(_session(total=80))
            await db_session.flush()
            guards = _Guards(db_session, backend, quota_bytes=100)
            await guards._check_quota(50, reserve=False)
            with pytest.raises(QuotaExceededError):
                await guards._check_quota(50, reserve=True)

    async def test_expired_and_finished_sessions_release_their_reservation(
        self, backend, db_session
    ):
        with tenant_context("t1"):
            db_session.add_all(
                [
                    _session(total=80, expires_in=-timedelta(minutes=1)),
                    _session(total=80, status=constants.UploadStatus.COMPLETED),
                    _session(total=80, status=constants.UploadStatus.ABORTED),
                ]
            )
            await db_session.flush()
            await _Guards(db_session, backend, quota_bytes=100)._check_quota(100, reserve=True)

    async def test_stored_and_reserved_bytes_add_up(self, backend, db_session):
        with tenant_context("t1"):
            db_session.add_all([_stored(30), _session(total=30)])
            await db_session.flush()
            guards = _Guards(db_session, backend, quota_bytes=100)
            await guards._check_quota(40, reserve=True)
            with pytest.raises(QuotaExceededError):
                await guards._check_quota(41, reserve=True)

    async def test_usage_is_per_tenant(self, backend, db_session):
        with tenant_context("t2"):
            db_session.add(_stored(1000))
            await db_session.flush()
        with tenant_context("t1"):
            await _Guards(db_session, backend, quota_bytes=100)._check_quota(100, reserve=True)

    async def test_reserve_takes_the_lock_before_reading_usage(
        self, backend, db_session, monkeypatch
    ):
        order: list[str] = []
        guards = _Guards(db_session, backend, quota_bytes=100)

        async def fake_lock(*, platform: bool = False) -> None:
            order.append("lock")

        monkeypatch.setattr(guards, "_serialize_reservations", fake_lock)
        with tenant_context("t1"):
            await guards._check_quota(1, reserve=True)
            await guards._check_quota(1, reserve=False)
        assert order == ["lock"]


def _db_on(dialect: str, calls: list[tuple[str, Any]]) -> SimpleNamespace:
    """A session stub on ``dialect`` that records every statement it executes."""

    async def execute(statement: object, params: Any = None) -> None:
        calls.append((str(statement), params))

    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    return SimpleNamespace(get_bind=lambda: bind, execute=execute)


class TestSerializeReservations:
    async def test_is_a_no_op_off_postgres(self, backend, db_session):
        executed: list[tuple[str, Any]] = []
        await _Guards(_db_on("sqlite", executed), backend)._serialize_reservations()
        assert executed == []

    async def test_takes_a_per_tenant_advisory_lock_on_postgres(self, backend, monkeypatch):
        calls: list[tuple[str, Any]] = []
        monkeypatch.setattr(guards_module, "owning_tenant", lambda db, platform=False: "acme")
        await _Guards(_db_on("postgresql", calls), backend)._serialize_reservations()
        monkeypatch.setattr(guards_module, "owning_tenant", lambda db, platform=False: "globex")
        await _Guards(_db_on("postgresql", calls), backend)._serialize_reservations()

        assert all("pg_advisory_xact_lock" in sql for sql, _ in calls)
        assert calls[0][1]["key"] != calls[1][1]["key"]
        assert calls[0][1]["key"] >> 32 == 0x4653544F
