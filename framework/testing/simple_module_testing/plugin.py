"""Pytest plugin — registered via the ``pytest11`` entry_point in pyproject.toml.

Fixtures declared here are available to every test run in any environment
that has ``simple_module_testing`` installed, without a ``conftest.py``
import. Delete a fixture from this file and you break external modules'
test suites — treat the fixture surface like a public API.
"""

from __future__ import annotations

import pytest

from simple_module_testing.app_factory import build_test_app as _build_test_app
from simple_module_testing.fake_events import FakeEventBus


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
