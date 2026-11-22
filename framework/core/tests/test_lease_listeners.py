"""Lifespan observers see backend replacements without changing public exports."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from simple_module_core.leases import (
    InProcessLeaseBackend,
    _add_lease_listener,
    _remove_lease_listener,
    configure_leases,
    get_leases,
)


def test_listeners_see_resets_and_stop_after_removal():
    seen = []
    listener = seen.append
    _add_lease_listener(listener)
    try:
        backend = InProcessLeaseBackend()
        configure_leases(backend)
        configure_leases(None)
        reset = get_leases()
        assert seen == [backend, reset]
        assert reset is not backend
    finally:
        _remove_lease_listener(listener)
    configure_leases(None)
    assert seen == [backend, reset]


def test_listener_can_remove_itself_during_notification():
    seen = []

    def listener(backend):
        seen.append(backend)
        _remove_lease_listener(listener)

    _add_lease_listener(listener)
    try:
        backend = InProcessLeaseBackend()
        configure_leases(backend)
        configure_leases(None)
        assert seen == [backend]
    finally:
        _remove_lease_listener(listener)


def test_concurrent_replacements_are_all_reported():
    seen = []
    listener = seen.append
    backends = [InProcessLeaseBackend() for _ in range(20)]
    _add_lease_listener(listener)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(configure_leases, backends))
        assert len(seen) == 20
        assert {id(backend) for backend in seen} == {id(backend) for backend in backends}
    finally:
        _remove_lease_listener(listener)


def test_listener_can_read_and_replace_backend_during_notification():
    initial, final = InProcessLeaseBackend(), InProcessLeaseBackend()
    seen = []

    def listener(backend):
        assert get_leases() is backend
        seen.append(backend)
        if backend is initial:
            configure_leases(final)

    _add_lease_listener(listener)
    try:
        configure_leases(initial)
        assert seen == [initial, final]
        assert get_leases() is final
    finally:
        _remove_lease_listener(listener)


def test_fork_while_listener_holds_lock_resets_child_lock():
    probe = """
import os, signal, threading
from simple_module_core.leases import (
    InProcessLeaseBackend,
    _add_lease_listener,
    _remove_lease_listener,
    configure_leases,
    get_leases,
)

held, release = threading.Event(), threading.Event()
seen = []

def slow_listener(_backend):
    held.set()
    release.wait(3)

_add_lease_listener(slow_listener)
thread = threading.Thread(target=configure_leases, args=(InProcessLeaseBackend(),))
thread.start()
assert held.wait(2)

pid = os.fork()
if pid == 0:
    signal.alarm(2)
    code = 1
    try:
        _remove_lease_listener(slow_listener)
        _add_lease_listener(seen.append)
        configure_leases(None)
        assert seen == [get_leases()]
        code = 0
    except BaseException:
        import traceback

        traceback.print_exc()
    finally:
        os._exit(code)

release.set()
thread.join(timeout=2)
_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 0
"""
    subprocess.run([sys.executable, "-c", probe], check=True, timeout=10)
