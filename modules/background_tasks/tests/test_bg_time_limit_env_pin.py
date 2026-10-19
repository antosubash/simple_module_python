"""An env-pinned hard time limit beside a stored soft limit at or above it (#548).

The pair rule is reported on ``task_time_limit``. With that field set by env,
lenient hydration could not drop it and re-raised: the web fell back to
defaults for every background_tasks override, and the worker would not start
on its DB config. The stored soft limit is the half to drop.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.worker_settings import clear_settings_cache, load_runner_settings
from settings.models import Setting
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_PREFIX = "background_tasks"


@pytest.fixture(autouse=True)
def _pinned_hard_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SM_BG_TASKS_TASK_TIME_LIMIT", "50")


@pytest.mark.asyncio
async def test_hydration_drops_the_stored_soft_limit(db_session, caplog) -> None:
    from settings.hydrate import hydrate_settings
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    await store.set_override(_PREFIX, "task_soft_time_limit", "100", "int")
    await store.set_override(_PREFIX, "max_retries", "7", "int")

    with caplog.at_level(logging.ERROR, logger="settings.hydrate"):
        cfg = await hydrate_settings(BackgroundTasksSettings, store, _PREFIX, lenient=True)

    assert (cfg.task_time_limit, cfg.task_soft_time_limit) == (50, None)
    assert cfg.max_retries == 7  # the module's other overrides survive
    assert "task_soft_time_limit" in caplog.text


@pytest.fixture
def db_url(tmp_path) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'pin.db'}"
    engine = create_engine(url)
    Setting.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Setting(key=f"{_PREFIX}.task_soft_time_limit", value="100", value_type="int"))
        s.add(Setting(key=f"{_PREFIX}.max_retries", value="7", value_type="int"))
        s.commit()
    engine.dispose()
    sync_db.set_database_url(url)
    clear_settings_cache()
    yield url
    sync_db.dispose_sync_engine()
    clear_settings_cache()


def test_worker_boots_on_its_db_config(db_url: str) -> None:
    cfg = load_runner_settings()

    assert (cfg.task_time_limit, cfg.task_soft_time_limit, cfg.max_retries) == (50, None, 7)
