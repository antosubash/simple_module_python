"""Real redis.asyncio socket-pair teardown regressions across loops and forks."""

import asyncio
import gc
import importlib.util
import os
import warnings

import pytest
from backend_cleanup_helpers import run_fork_probe

_HAS_UVLOOP = importlib.util.find_spec("uvloop") is not None
_FORK_ONLY = pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
_UVLOOP_ONLY = pytest.mark.skipif(not _HAS_UVLOOP, reason="requires uvloop")

_FORK_PROBE = """
import asyncio, os, socket, stat
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

owner = __import__("uvloop").new_event_loop() if mode == "uvloop" else asyncio.new_event_loop()
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


@_UVLOOP_ONLY
def test_closed_uvloop_real_redis_transport_retires_without_type_error():
    import uvloop

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


@pytest.mark.parametrize("closing_first", [False, True])
@pytest.mark.parametrize("factory_name", ["stdlib", pytest.param("uvloop", marks=_UVLOOP_ONLY)])
def test_stopped_owner_real_redis_transport_retires_socket_and_resumes_cleanly(
    factory_name, closing_first
):
    backend, created, attach_stream, s1, s2 = _pooled_socket_backend()
    owner = (
        __import__("uvloop").new_event_loop()
        if factory_name == "uvloop"
        else asyncio.new_event_loop()
    )
    loop_errors = []
    owner.set_exception_handler(lambda loop, ctx: loop_errors.append(ctx))
    try:
        conn = owner.run_until_complete(attach_stream())
        pool = created[0].connection_pool
        if closing_first:
            conn._writer.close()
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


@_FORK_ONLY
@pytest.mark.parametrize(
    "mode", ["stopped_stdlib", "running_stdlib", pytest.param("uvloop", marks=_UVLOOP_ONLY)]
)
def test_real_fork_closes_child_fd_without_breaking_parent_selector(mode):
    run_fork_probe(_FORK_PROBE, mode)


@pytest.mark.parametrize("stop_when", ["before_abort", "after_abort"])
def test_owner_resumes_then_stops_during_abort_still_closes_socket(stop_when):
    from threading import Event, Thread

    backend, _created, attach_stream, s1, s2 = _pooled_socket_backend()
    owner = asyncio.new_event_loop()
    loop_errors = []
    owner.set_exception_handler(lambda loop, ctx: loop_errors.append(ctx))
    block_entered, release_blocker, aborted = Event(), Event(), Event()
    thread = None

    def block_in_owner():
        block_entered.set()
        assert release_blocker.wait(3)

    async def exercise():
        nonlocal thread
        current = asyncio.get_running_loop()
        abort_queued = asyncio.Event()
        orig_call_soon = owner.call_soon_threadsafe

        def intercept_abort(*args, **kwargs):
            handle = orig_call_soon(*args, **kwargs)
            if args and getattr(args[0], "__name__", None) == "run_abort":
                current.call_soon_threadsafe(abort_queued.set)
            return handle

        owner.call_soon_threadsafe = intercept_abort
        close_task = asyncio.create_task(backend.aclose())
        await asyncio.sleep(0)  # allow aclose() to pick stopped owner's fallback host
        owner.call_soon(block_in_owner)
        thread = Thread(
            target=lambda: (asyncio.set_event_loop(owner), owner.run_forever()), daemon=True
        )
        thread.start()
        assert block_entered.wait(2)
        await asyncio.wait_for(abort_queued.wait(), 2)
        if stop_when == "before_abort":
            owner.stop()
        release_blocker.set()
        thread.join(timeout=2)
        assert not thread.is_alive()
        if stop_when == "after_abort":
            assert aborted.is_set()
        await asyncio.wait_for(close_task, 2)

    try:
        conn = owner.run_until_complete(attach_stream())
        if stop_when == "after_abort":
            orig_abort = conn._writer.transport.abort

            def abort_and_stop():
                try:
                    orig_abort()
                    owner.stop()
                finally:
                    aborted.set()

            conn._writer.transport.abort = abort_and_stop
        asyncio.run(exercise())
        assert backend._records == []
        assert s1.fileno() == -1
        owner.run_until_complete(asyncio.sleep(0))
        assert loop_errors == []
    finally:
        release_blocker.set()
        if thread is not None and thread.is_alive():
            owner.call_soon_threadsafe(owner.stop)
            thread.join(timeout=2)
        owner.close()
        s2.close()
