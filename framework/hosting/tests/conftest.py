"""Hosting test isolation."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from simple_module_hosting.observability import sentry as sm_sentry


@pytest.fixture(autouse=True)
def _sentry_flag_does_not_leak() -> Iterator[None]:
    """``init_sentry`` flips a module global that changes ``create_app``'s middleware."""
    yield
    sm_sentry._enabled = False


@pytest.fixture
def isolated_host_root(tmp_path, monkeypatch):
    """Dev boot writes artifacts, so give it a private host and i18n output tree."""
    import shutil
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    shutil.copytree(repo / "host/templates", tmp_path / "host/templates")
    (tmp_path / "host/client_app").mkdir()
    shutil.copy2(repo / "host/client_app/tsconfig.json", tmp_path / "host/client_app/tsconfig.json")
    (tmp_path / "packages/i18n/src").mkdir(parents=True)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    return tmp_path
