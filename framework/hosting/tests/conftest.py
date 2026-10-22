"""Hosting test isolation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from simple_module_hosting import sentry as sm_sentry


@pytest.fixture(autouse=True)
def _sentry_flag_does_not_leak() -> Iterator[None]:
    """``init_sentry`` flips a module global that changes ``create_app``'s middleware."""
    yield
    sm_sentry._enabled = False
