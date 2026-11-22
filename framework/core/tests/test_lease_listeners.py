"""Lifespan observers see backend replacements without changing public exports."""

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
