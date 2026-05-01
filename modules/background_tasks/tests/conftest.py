"""Shared fixtures for background_tasks tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
async def _stub_celery(app) -> None:
    """Replace the real Celery instance with a MagicMock.

    Opt-in via ``pytestmark = pytest.mark.usefixtures("_stub_celery")`` at
    module scope — not autouse, because signal tests deliberately exercise
    an unstarted app and would be broken by the implicit ``app`` dependency.
    ``send_task.return_value.id`` is pre-set so retry flows that read it
    (see ``test_admin_api.py``) work without further setup.
    """
    celery = MagicMock(name="Celery")
    celery.send_task.return_value.id = "mocked-celery-id"
    app.state.background_tasks.celery = celery
