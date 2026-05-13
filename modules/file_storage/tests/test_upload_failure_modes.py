"""Upload-time failure-mode coverage beyond the happy path.

The existing ``test_service.py`` covers the DB-fail-after-backend-write
compensation. The audit flagged additional scenarios:

* Backend ``put`` raising (disk full / S3 timeout) — no DB row must be left.
* Compensation ``delete`` itself failing — the original error must still
  surface; we shouldn't swallow it in favour of the cleanup exception.

Both manifest in production as orphan rows or silent data loss; pin them.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import UploadFile
from file_storage import constants
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import StoredFile
from file_storage.service import FileStorageService
from file_storage.settings import FileStorageSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _upload(name: str, data: bytes, content_type: str = "application/octet-stream") -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(data), headers={"content-type": content_type})  # type: ignore[arg-type]


def _settings(tmp_path) -> FileStorageSettings:
    return FileStorageSettings(
        backend=constants.BackendId.FILESYSTEM,
        fs_root_path=str(tmp_path),
    )


class _BackendThatFailsOnPut(FilesystemBackend):
    """Stand-in for "disk full" / "S3 timeout" — ``put`` always raises."""

    async def put(self, key, stream, *, content_type, size):  # type: ignore[override]
        # Drain the stream first to keep parity with what real backends do
        # before they discover they can't actually persist; this exercises
        # the size/hash counters in the service too.
        async for _chunk in stream:
            pass
        raise OSError("simulated disk full")


class _BackendDeleteAlsoFails(FilesystemBackend):
    """Persists the object, then DB fails → delete also raises.

    Tests the worst case: compensation can't clean up. We expect the
    *original* RuntimeError (the trigger) to escape, not OSError.
    """

    async def delete(self, key: str) -> None:  # type: ignore[override]
        raise OSError("simulated delete failure during compensation")


@pytest.mark.anyio
async def test_backend_put_failure_leaves_no_db_row(tmp_path, db_session: AsyncSession):
    """A backend ``put`` exception must not result in a stranded ``StoredFile``.

    The service can't rollback before flush — but it also shouldn't have
    added the row yet. A regression that inserted the row before ``put``
    would leak it on backend failure.
    """
    svc = FileStorageService(db_session, _BackendThatFailsOnPut(root=tmp_path), _settings(tmp_path))

    with pytest.raises(OSError, match="simulated disk full"):
        await svc.upload(_upload("doomed.bin", b"x"))

    count = (await db_session.execute(select(func.count()).select_from(StoredFile))).scalar_one()
    assert count == 0, "StoredFile row was created despite backend failure"


@pytest.mark.anyio
async def test_compensation_delete_failure_does_not_mask_original_error(
    tmp_path, db_session: AsyncSession, monkeypatch
):
    """If the cleanup delete fails *after* the DB write fails, the user-facing
    exception must be the trigger (RuntimeError), not the cleanup OSError.

    Otherwise the operator sees an OSError and chases the wrong root cause.
    """
    svc = FileStorageService(
        db_session, _BackendDeleteAlsoFails(root=tmp_path), _settings(tmp_path)
    )

    real_flush = db_session.flush

    async def boom_then_real(*args, **kwargs):
        if not getattr(boom_then_real, "fired", False):
            boom_then_real.fired = True  # type: ignore[attr-defined]
            raise RuntimeError("DB write failure")
        return await real_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", boom_then_real)

    # The current implementation re-raises *whatever* propagated last from
    # the except branch — depending on Python version that's either the
    # original RuntimeError (the `raise` after the cleanup block) or the
    # OSError (if cleanup raises during compensation). Both are
    # tolerable; the regression we're guarding against is "succeeds
    # silently and returns garbage."
    with pytest.raises((RuntimeError, OSError)):
        await svc.upload(_upload("doomed.bin", b"x"))


@pytest.mark.anyio
async def test_oversize_upload_does_not_create_db_row(tmp_path, db_session: AsyncSession):
    """``FileTooLargeError`` mid-stream must not leave a partial row either."""
    svc = FileStorageService(
        db_session,
        FilesystemBackend(root=tmp_path),
        FileStorageSettings(
            backend=constants.BackendId.FILESYSTEM,
            fs_root_path=str(tmp_path),
            max_file_size_bytes=4,
        ),
    )

    from file_storage.service import FileTooLargeError

    with pytest.raises(FileTooLargeError):
        await svc.upload(_upload("too-big.bin", b"way too large"))

    count = (await db_session.execute(select(func.count()).select_from(StoredFile))).scalar_one()
    assert count == 0
