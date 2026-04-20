"""Shared fixtures for the datasets test suite.

``BackgroundTasksModule.on_startup`` builds a live Celery app wired to
Redis. The datasets upload endpoint enqueues via ``send_task`` — against
a real Celery that'd require a broker in CI, which we don't want. Stub
it with a MagicMock so ``send_task`` is a recordable no-op; tests that
want to verify extraction drive ``extract_metadata_task`` directly.

This mirrors the pattern used in
``modules/background_tasks/tests/test_admin_api.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
async def _stub_celery(app) -> None:
    celery = MagicMock(name="Celery")
    celery.send_task.return_value.id = "mocked-celery-id"
    app.state.background_tasks.celery = celery
