"""Pytest plugin — registered via the ``pytest11`` entry_point in pyproject.toml.

Fixtures declared here are available to every test run in any environment
that has ``simple_module_test`` installed, without a ``conftest.py``
import. Delete a fixture from this file and you break external modules'
test suites — treat the fixture surface like a public API.
"""

from __future__ import annotations

import contextlib

import pytest

from simple_module_test.app_factory import build_test_app as _build_test_app
from simple_module_test.fake_events import FakeEventBus


def _bootstrap_eager_celery() -> None:
    """Register a process-wide eager Celery app before any test runs.

    Tests that don't use the ``client`` fixture never trigger the lifespan,
    so the host's ``build_celery`` call never runs and ``task.delay()``
    falls through to the broker. Skipped silently when ``background_tasks``
    isn't installed.
    """
    with contextlib.suppress(ImportError):
        from background_tasks.celery_app import build_celery
        from background_tasks.settings import BackgroundTasksSettings

        build_celery(BackgroundTasksSettings(task_always_eager=True, task_eager_propagates=True))


_bootstrap_eager_celery()


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
