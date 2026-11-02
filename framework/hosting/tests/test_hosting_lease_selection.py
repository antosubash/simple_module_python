"""Which lease backend a process gets (GH #539)."""

from __future__ import annotations

import pytest
from simple_module_core.leases import InProcessLeaseBackend, configure_leases, get_leases
from simple_module_db.leases import DbLeaseBackend
from simple_module_hosting.leases import (
    RedisLeaseBackend,
    build_lease_backend,
    configure_process_leases,
)


@pytest.fixture(autouse=True)
def _restore_default():
    yield
    configure_leases(None)


def test_redis_wins_when_configured(engine) -> None:
    backend = build_lease_backend("redis://localhost:6379/0", engine=engine)
    assert isinstance(backend, RedisLeaseBackend)


def test_database_engine_without_redis(engine) -> None:
    assert isinstance(build_lease_backend(None, engine=engine), DbLeaseBackend)


async def test_database_url_builds_its_own_engine(tmp_path) -> None:
    backend = build_lease_backend(None, database_url=f"sqlite+aiosqlite:///{tmp_path}/l.db")
    assert isinstance(backend, DbLeaseBackend)
    await backend._engine.dispose()


def test_nothing_configured_is_in_process() -> None:
    assert isinstance(build_lease_backend(None), InProcessLeaseBackend)


def test_configure_process_leases_installs_it(engine) -> None:
    backend = configure_process_leases(None, engine=engine)
    assert get_leases() is backend


async def test_create_app_installs_the_database_backend(app) -> None:
    backend = get_leases()
    assert isinstance(backend, DbLeaseBackend)
    assert backend._engine is app.state.sm.db.engine
