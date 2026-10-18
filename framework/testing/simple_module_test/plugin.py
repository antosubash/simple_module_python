"""Pytest plugin — registered via the ``pytest11`` entry_point in pyproject.toml.

Fixtures declared here are available to every test run in any environment
that has ``simple_module_test`` installed, without a ``conftest.py``
import. Delete a fixture from this file and you break external modules'
test suites — treat the fixture surface like a public API.
"""

from __future__ import annotations

import contextlib
import os

import pytest

from simple_module_test.app_factory import build_test_app as _build_test_app
from simple_module_test.fake_events import FakeEventBus

# Re-export the headline app/db/client fixtures the README advertises. pytest
# collects fixture-decorated attributes of the plugin module, so importing them
# here registers them for every test run that installs simple_module_test —
# without a per-consumer conftest. Treat this surface like a public API: deleting
# one breaks external modules' suites. See GH #200.
from simple_module_test.fixtures import (  # noqa: F401
    app,
    authenticated_client,
    client,
    db_session,
    db_state,
    engine,
    fresh_test_database,
    pinned_auth_provider,
    settings,
    setup_pending_app,
)
from simple_module_test.redis_server import redis_server  # noqa: F401
from simple_module_test.tenant_client import tenant_client  # noqa: F401


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgres: needs a PostgreSQL test database (SM_TEST_DATABASE_URL=postgresql+...)",
    )
    from simple_module_test.database import database_is_postgres

    # Every Postgres test drops and recreates ``public`` in the one database, so
    # xdist workers would wipe each other's schema mid-test.
    if database_is_postgres() and getattr(config.option, "numprocesses", None):
        raise pytest.UsageError(
            "SM_TEST_DATABASE_URL is Postgres, whose schema every test drops: run "
            "serially with `make test-py-pg` or `-n 0` (`PYTEST_WORKERS=0 make test-py`)"
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``@pytest.mark.postgres`` tests unless the test database is Postgres."""
    from simple_module_test.database import database_is_postgres

    if database_is_postgres():
        return
    skip = pytest.mark.skip(
        reason="needs Postgres: set SM_TEST_DATABASE_URL=postgresql+asyncpg://..."
    )
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


def _bootstrap_eager_celery() -> None:
    """Register a process-wide eager Celery app before any test runs.

    Tests that don't use the ``client`` fixture never trigger the lifespan,
    so the host's ``build_celery`` call never runs and ``task.delay()``
    falls through to the broker. Skipped silently when ``background_tasks``
    isn't installed.

    Also switches off the cross-worker invalidation transport. ``on_startup``
    would otherwise open a Redis pub/sub listener per app fixture — against a
    broker no test environment runs — leaving a reconnect loop in the
    background of every suite. ``setdefault``, so a test that wants the transport
    can set the variable and get it — though the tests that exercise the transport
    build ``RedisInvalidationTransport`` directly instead, against either a fake
    client (``test_bg_invalidation.py``) or a throwaway ``redis-server`` (the
    ``redis_server`` fixture, used by ``test_bg_invalidation_redis.py``).
    """
    os.environ.setdefault("SM_BG_TASKS_BROADCAST_INVALIDATIONS", "false")
    with contextlib.suppress(ImportError):
        from background_tasks.celery_app import build_celery
        from background_tasks.settings import BackgroundTasksSettings

        build_celery(BackgroundTasksSettings(task_always_eager=True, task_eager_propagates=True))


_bootstrap_eager_celery()


def _cheap_password_hashing() -> None:
    """Make ``PasswordHelper()`` hash with minimal Argon2/bcrypt cost.

    Every ``app`` fixture seeds an admin, and production-cost Argon2 is ~90ms
    of CPU per hash — over a tenth of each app's setup, paid thousands of times
    a run. The hashes stay real ``$argon2``/``$2b`` strings that verify and
    upgrade through the same code paths; only their work factor drops, which is
    a property of deployment rather than anything a test asserts.

    Patched at import, not in a fixture: test modules build ``PasswordHelper()``
    at module scope during collection, before any fixture runs. An explicit
    ``password_hash=`` still wins. Skipped when ``fastapi_users`` is absent, or
    when ``SM_TEST_REAL_PASSWORD_HASHING`` is set — the opt-out for a consumer
    suite whose tests depend on production hash parameters.
    """
    if os.environ.get("SM_TEST_REAL_PASSWORD_HASHING"):
        return
    try:
        from fastapi_users.password import PasswordHelper
        from pwdlib import PasswordHash
        from pwdlib.hashers.argon2 import Argon2Hasher
        from pwdlib.hashers.bcrypt import BcryptHasher
    except ImportError:
        return

    original_init = PasswordHelper.__init__

    def _init(self, password_hash: PasswordHash | None = None) -> None:
        if password_hash is None:
            password_hash = PasswordHash(
                (
                    Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),
                    BcryptHasher(rounds=4),
                )
            )
        original_init(self, password_hash)

    PasswordHelper.__init__ = _init  # type: ignore[method-assign]


_cheap_password_hashing()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    """Fresh recording EventBus for each test."""
    return FakeEventBus()


@pytest.fixture
def build_test_app():
    """Callable that wraps a module class in a minimal FastAPI app.

    Exposed as a fixture (not a direct import) so tests can compose it with
    other fixtures via pytest's dependency resolution.
    """
    return _build_test_app
