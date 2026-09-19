"""A throwaway ``redis-server`` for tests that need a real broker.

The cross-worker invalidation transport is the one piece of this framework whose
whole job happens *between* processes, and a fake client cannot show that it
works — it can only show that this repo's own retry and teardown logic behaves.
So the tests that matter start a real server.

Deliberately a subprocess rather than a Docker service or the shared
``dev-services`` stack: a unit-test job that runs ``make install-py`` and nothing
else must be able to run these, and a developer must not have to bring anything
up first. The server is ephemeral — a free port, no persistence
(``--save '' --appendonly no``), killed on teardown — so it cannot collide with
the real ``dev-services`` Redis on 6379 or leave state behind.

Absent the binary the fixture **skips loudly** rather than passing vacuously.
``redis-server`` is present on GitHub's ``ubuntu-latest`` image, so these run in
CI; that they ran rather than skipped is worth confirming from the collected
count rather than assuming.
"""

from __future__ import annotations

import contextlib
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator

import pytest

__all__ = ["redis_server"]

_STARTUP_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.05


def _free_port() -> int:
    """A port nothing is listening on, as of a moment ago.

    Inherently racy — the port could be taken between the probe and the bind —
    but the alternative is a fixed port, which collides with a developer's own
    Redis and with a parallel test run. ``redis-server`` fails loudly on a taken
    port, and :func:`_wait_until_ready` turns that into a clear timeout rather
    than a hang.
    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(process: subprocess.Popen, port: int) -> None:
    """Block until the server accepts a connection, or fail with its output.

    Polls a TCP connect rather than shelling out to ``redis-cli``: one less
    binary to require, and the thing under test is whether a socket opens.
    """
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = (process.stdout.read() if process.stdout else "") or "(no output)"
            raise RuntimeError(f"redis-server exited during startup: {output}")
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
            return
        time.sleep(_POLL_INTERVAL_SECONDS)
    process.kill()
    raise RuntimeError(f"redis-server did not accept connections on {port} in time")


@pytest.fixture(scope="session")
def redis_server() -> Iterator[str]:
    """A URL for a private, empty Redis. Session-scoped — startup costs ~50ms.

    Session scope means tests share one server, so anything that would leave a
    subscription or a key behind must clean up after itself. Pub/sub carries no
    state between messages, which is why sharing is safe for the invalidation
    tests; a test that wrote keys would want its own database index.
    """
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server is not installed; cannot test the real transport")

    port = _free_port()
    process = subprocess.Popen(
        [
            binary,
            "--port",
            str(port),
            "--bind",
            "127.0.0.1",
            # No persistence: nothing to write, nothing to load, no dump.rdb
            # dropped into whatever directory pytest happened to run from.
            "--save",
            "",
            "--appendonly",
            "no",
            "--databases",
            "1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_until_ready(process, port)
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        if process.poll() is None:
            process.kill()
        if process.stdout is not None:
            process.stdout.close()
