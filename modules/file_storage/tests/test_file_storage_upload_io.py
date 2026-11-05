"""Upload I/O must leave the event loop free and close resources safely."""

import asyncio
import threading
from tempfile import SpooledTemporaryFile

import pytest
from file_storage.backends import s3_put
from test_file_storage_server_put import chunks
from test_file_storage_server_put import wire_backend as wire_backend


@pytest.mark.parametrize("size", [0, 6, 10])
async def test_spool_io_runs_off_loop(wire_backend, monkeypatch, size):
    loop_thread = threading.get_ident()
    calls = []

    class CheckedSpool(SpooledTemporaryFile):
        def _note(self, extra=0):
            disk = self._rolled or self.tell() + extra > self._max_size
            calls.append((threading.get_ident(), disk))

        def write(self, s):
            self._note(len(s))
            return super().write(s)

        def read(self, n=-1, /):
            self._note()
            return super().read(n)

        def seek(self, offset, whence=0):
            self._note()
            return super().seek(offset, whence)

        def truncate(self, size=None):
            self._note()
            return super().truncate(size)

        def close(self):
            self._note()
            return super().close()

    monkeypatch.setattr(s3_put, "SpooledTemporaryFile", CheckedSpool)
    monkeypatch.setattr(s3_put.constants, "SPOOL_MAX_SIZE_BYTES", 2)
    wire, backend = wire_backend

    async def put_object(**kw):
        wire.single = await asyncio.to_thread(kw["Body"].read)

    async def upload_part(**kw):
        wire.parts.append(await asyncio.to_thread(kw["Body"].read))
        return {"ETag": str(kw["PartNumber"])}

    monkeypatch.setattr(wire, "put_object", put_object)
    monkeypatch.setattr(wire, "upload_part", upload_part)
    payload = b"123456" if size == 6 else b"1234567890"
    await backend.put("key", chunks(payload), content_type="text/plain", size=size)
    assert (wire.single if size == 6 else b"".join(wire.parts)) == payload
    # In-memory operations run inline by design; anything on disk must be off-loop.
    assert any(thread != loop_thread for thread, _ in calls)
    assert all(thread != loop_thread for thread, disk in calls if disk)


@pytest.mark.parametrize("fail_completion", [False, True])
async def test_multipart_reuses_one_client(wire_backend, monkeypatch, fail_completion):
    wire, backend = wire_backend
    if fail_completion:
        wire.failure = RuntimeError("complete failed")
        with pytest.raises(Exception, match="complete failed"):
            await backend.put("key", chunks(b"12345678901"), content_type="text/plain", size=0)
        assert wire.aborted
    else:
        await backend.put("key", chunks(b"12345678901"), content_type="text/plain", size=0)
    assert b"".join(wire.parts) == b"12345678901"
    assert wire.opened == wire.closed == 1


@pytest.mark.parametrize("cancel_count", [1, 2])
@pytest.mark.parametrize("write_fails", [False, True])
async def test_cancellation_waits_for_write_before_closing(
    wire_backend, monkeypatch, cancel_count, write_fails
):
    entered = threading.Event()
    release = threading.Event()
    files = []

    class SlowSpool(SpooledTemporaryFile):
        def __init__(self, **kw):
            super().__init__(**kw)
            files.append(self)

        def write(self, s):
            entered.set()
            assert release.wait(3)
            assert not self.closed
            if write_fails:
                raise OSError("disk failed after cancellation")
            return super().write(s)

    monkeypatch.setattr(s3_put, "SpooledTemporaryFile", SlowSpool)
    # Writes that stay in memory run inline; force the disk path this test models.
    monkeypatch.setattr(s3_put.constants, "SPOOL_MAX_SIZE_BYTES", 1)
    wire, backend = wire_backend
    backend.multipart_threshold_bytes = 1
    task = asyncio.create_task(
        backend.put("key", chunks(b"1234567"), content_type="text/plain", size=7)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        for _ in range(cancel_count):
            task.cancel()
            await asyncio.sleep(
                0.01
            )  # intentional-sleep: expose premature close while I/O is blocked
            assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert files and all(f.closed for f in files)
    assert wire.aborted and wire.completed is None


async def test_io_task_cancelled_by_loop_shutdown_does_not_spin():
    """Cancelling the inner executor task (as loop shutdown does) must propagate."""
    gate = threading.Event()
    waiter = asyncio.create_task(s3_put._io(gate.wait, 3))
    await asyncio.sleep(0.01)
    inner = next(
        t for t in asyncio.all_tasks() if t is not waiter and t is not asyncio.current_task()
    )
    inner.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(waiter, 2)
    finally:
        gate.set()
