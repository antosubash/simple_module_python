"""Real redis.asyncio socket-pair teardown regressions across loops and forks."""

import asyncio
import gc
import subprocess
import sys
import warnings

import pytest
import uvloop

_FORK_PROBE = """
import asyncio, os, socket, stat, uvloop
from threading import Event, Thread
import redis.asyncio as aioredis
from simple_module_hosting._lease_redis import RedisLeaseBackend

mode = __import__("sys").argv[1]
s1, s2 = socket.socketpair()
created = []

def factory():
    c = aioredis.from_url("redis://localhost:6379/0")
    created.append(c)
    return c

backend = RedisLeaseBackend("redis://localhost:6379/0", factory=factory)

async def attach_stream():
    client = backend._redis()
    conn = client.connection_pool.make_connection()
    reader, writer = await asyncio.open_connection(sock=s1)
    conn._reader = reader
    conn._writer = writer
    conn._parser._stream = reader
    client.connection_pool._available_connections.append(conn)
    return writer, writer.transport

owner = uvloop.new_event_loop() if mode == "uvloop" else asyncio.new_event_loop()
ready = Event()
writer, transport = owner.run_until_complete(attach_stream())
raw_fd = transport.get_extra_info("socket").fileno()

thread = None
if mode == "running_stdlib":
    def serve():
        asyncio.set_event_loop(owner)
        owner.call_soon(ready.set)
        owner.run_forever()
    thread = Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(2)

pid = os.fork()
if pid == 0:
    code = 1
    try:
        asyncio.run(backend.aclose())
        assert backend._records == []
        if mode == "uvloop":
            assert not stat.S_ISSOCK(os.fstat(raw_fd).st_mode)
        else:
            try:
                os.fstat(raw_fd)
            except OSError:
                pass
            else:
                raise AssertionError("expected stdlib fork fd closed")
        new_a, new_b = socket.socketpair()
        try:
            if mode != "running_stdlib":
                owner.close()
            new_a.send(b"ok")
            assert new_b.recv(2) == b"ok"
            code = 0
        finally:
            new_a.close()
            new_b.close()
    except BaseException:
        import traceback

        traceback.print_exc()
    finally:
        os._exit(code)

_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 0

async def verify_parent():
    writer.write(b"ping")
    await writer.drain()
    return await asyncio.to_thread(s2.recv, 4)

if mode == "running_stdlib":
    import concurrent.futures
    fut = asyncio.run_coroutine_threadsafe(verify_parent(), owner)
    assert fut.result(timeout=2) == b"ping"
    owner.call_soon_threadsafe(owner.stop)
    thread.join(timeout=5)
else:
    assert owner.run_until_complete(verify_parent()) == b"ping"
owner.close()
s2.close()
"""


def _pooled_socket_backend():
    import socket

    import redis.asyncio as aioredis
    from simple_module_hosting._lease_redis import RedisLeaseBackend

    s1, s2 = socket.socketpair()
    created = []

    def factory():
        client = aioredis.from_url("redis://localhost:6379/0")
        created.append(client)
        return client

    backend = RedisLeaseBackend("redis://localhost:6379/0", factory=factory)

    async def attach_stream():
        client = backend._redis()
        conn = client.connection_pool.make_connection()
        reader, writer = await asyncio.open_connection(sock=s1)
        conn._reader = reader
        conn._writer = writer
        conn._parser._stream = reader
        client.connection_pool._available_connections.append(conn)
        return conn

    return backend, created, attach_stream, s1, s2


def test_closed_owner_real_redis_transport_releases_socket_without_errors():
    backend, created, attach_stream, s1, s2 = _pooled_socket_backend()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            conn = asyncio.run(attach_stream())
            pool = created[0].connection_pool
            assert s1.fileno() != -1
            asyncio.run(backend.aclose())
            assert conn._parser._stream is None
            assert pool._available_connections == []
            assert pool._in_use_connections == set()
            del conn, pool, created[:]
            gc.collect()
        assert backend._records == []
        assert s1.fileno() == -1
        assert not [w for w in caught if issubclass(w.category, ResourceWarning)]
    finally:
        s2.close()


def test_closed_uvloop_real_redis_transport_retires_without_type_error():
    backend, created, attach_stream, s1, s2 = _pooled_socket_backend()
    owner = uvloop.new_event_loop()
    try:
        conn = owner.run_until_complete(attach_stream())
        pool = created[0].connection_pool
        owner.close()
        asyncio.run(backend.aclose())
        assert backend._records == []
        assert s1.fileno() == -1
        assert conn._parser._stream is None
        assert pool._available_connections == []
        assert pool._in_use_connections == set()
    finally:
        if not owner.is_closed():
            owner.close()
        s2.close()


@pytest.mark.parametrize("factory", [asyncio.new_event_loop, uvloop.new_event_loop])
def test_stopped_owner_real_redis_transport_retires_socket_and_resumes_cleanly(factory):
    backend, created, attach_stream, s1, s2 = _pooled_socket_backend()
    owner = factory()
    loop_errors = []
    owner.set_exception_handler(lambda loop, ctx: loop_errors.append(ctx))
    try:
        conn = owner.run_until_complete(attach_stream())
        pool = created[0].connection_pool
        assert s1.fileno() != -1
        asyncio.run(backend.aclose())
        assert backend._records == []
        assert s1.fileno() == -1
        assert conn._parser._stream is None
        assert pool._available_connections == []
        assert pool._in_use_connections == set()
        # Resuming the stopped owner loop later must not raise selector or transport errors.
        owner.run_until_complete(asyncio.sleep(0))
        assert loop_errors == []
    finally:
        owner.close()
        s2.close()


def _run_probe(script, arg):
    result = subprocess.run(
        [sys.executable, "-c", script, arg], check=False, capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"


@pytest.mark.parametrize("mode", ["stopped_stdlib", "running_stdlib", "uvloop"])
def test_real_fork_closes_child_fd_without_breaking_parent_selector(mode):
    _run_probe(_FORK_PROBE, mode)


_QUARANTINE_FAILURE_PROBE = """
import asyncio, errno, os, socket, stat, traceback, uvloop
from unittest.mock import patch
import redis.asyncio as aioredis
from simple_module_hosting._lease_redis import RedisLeaseBackend

s1, s2 = socket.socketpair()
backend = RedisLeaseBackend("redis://localhost:6379/0", factory=lambda: aioredis.from_url("redis://localhost:6379/0"))

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
            before_fds = len(os.listdir("/proc/self/fd"))
            with patch("os.dup2", side_effect=OSError(errno.EIO, "dup2 failed")):
                assert_raises_errno(errno.EIO)
            assert len(os.listdir("/proc/self/fd")) == before_fds
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


@pytest.mark.parametrize("scenario", ["owner_close_first", "retry_after_dup2_failure"])
def test_real_fork_uvloop_quarantine_failure_preserves_fd_and_retries(scenario):
    _run_probe(_QUARANTINE_FAILURE_PROBE, scenario)
