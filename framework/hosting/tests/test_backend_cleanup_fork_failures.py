"""Quarantine failure regressions for forked uvloop transports (#1083)."""

import importlib.util
import os

import pytest
from backend_cleanup_helpers import run_fork_probe

_QUARANTINE_FAILURE_PROBE = """
import asyncio, errno, os, socket, stat, traceback, uvloop
from unittest.mock import patch
import redis.asyncio as aioredis
from simple_module_hosting._lease_redis import RedisLeaseBackend

s1, s2 = socket.socketpair()
url = "redis://localhost:6379/0"
backend = RedisLeaseBackend(url, factory=lambda: aioredis.from_url(url))

async def attach_stream():
    client = backend._redis()
    conn = client.connection_pool.make_connection()
    reader, writer = await asyncio.open_connection(sock=s1)
    conn._reader, conn._writer, conn._parser._stream = reader, writer, reader
    client.connection_pool._available_connections.append(conn)
    return writer.transport

owner = uvloop.new_event_loop()
raw_fd = owner.run_until_complete(attach_stream()).get_extra_info("socket").fileno()
scenario, real_open = __import__("sys").argv[1], os.open

def fail_devnull(path, *args, **kwargs):
    if path == os.devnull:
        raise OSError(errno.EMFILE, "too many open files")
    return real_open(path, *args, **kwargs)

def assert_raises_errno(expected):
    try:
        asyncio.run(backend.aclose())
    except OSError as exc:
        assert exc.errno == expected, exc
    else:
        raise AssertionError(f"expected errno {expected}")

pid = os.fork()
if pid == 0:
    code, spare_fd, new_a, new_b = 1, None, None, None
    try:
        if scenario == "owner_close_first":
            with patch("os.open", side_effect=fail_devnull):
                assert_raises_errno(errno.EMFILE)
        else:
            fd_dir = next((p for p in ("/proc/self/fd", "/dev/fd") if os.path.isdir(p)), None)
            before_fds = len(os.listdir(fd_dir)) if fd_dir else None
            with patch("os.dup2", side_effect=OSError(errno.EIO, "dup2 failed")):
                assert_raises_errno(errno.EIO)
            if before_fds is not None:
                assert len(os.listdir(fd_dir)) == before_fds
        assert len(backend._records) == 1
        assert not backend._records[0].closed and backend._records[0].future is None
        assert stat.S_ISSOCK(os.fstat(raw_fd).st_mode)
        spare_fd = os.open(os.devnull, os.O_RDONLY)
        new_a, new_b = socket.socketpair()
        assert raw_fd not in (spare_fd, new_a.fileno(), new_b.fileno())
        if scenario == "retry_after_dup2_failure":
            asyncio.run(backend.aclose())
            assert backend._records == [] and not stat.S_ISSOCK(os.fstat(raw_fd).st_mode)
        owner.close()
        os.fstat(spare_fd)
        new_a.send(b"ok")
        assert new_b.recv(2) == b"ok"
        if scenario == "owner_close_first":
            asyncio.run(backend.aclose())
            assert backend._records == []
        code = 0
    except BaseException:
        traceback.print_exc()
    finally:
        if spare_fd is not None:
            os.close(spare_fd)
        for sock in (new_a, new_b):
            if sock is not None:
                sock.close()
        os._exit(code)

_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 0
owner.close()
s2.close()
"""


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.skipif(importlib.util.find_spec("uvloop") is None, reason="requires uvloop")
@pytest.mark.parametrize("scenario", ["owner_close_first", "retry_after_dup2_failure"])
def test_real_fork_uvloop_quarantine_failure_preserves_fd_and_retries(scenario):
    run_fork_probe(_QUARANTINE_FAILURE_PROBE, scenario)
