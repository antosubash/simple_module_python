"""The worker/beat process hydrates DB-backed settings at boot (GH #447-#450 follow-up)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.worker_settings import clear_settings_cache, load_runner_settings
from settings.models import Setting
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_url(tmp_path) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'r.db'}"
    engine = create_engine(url)
    Setting.metadata.create_all(engine)
    sync_db.set_database_url(url)
    clear_settings_cache()
    yield url
    sync_db.dispose_sync_engine()
    clear_settings_cache()
    engine.dispose()


def _put(url: str, key: str, value: str, vtype: str) -> None:
    engine = create_engine(url)
    with Session(engine) as s:
        s.add(Setting(key=key, value=value, value_type=vtype))
        s.commit()
    engine.dispose()


def test_db_overrides_reach_the_worker(db_url: str) -> None:
    _put(db_url, "background_tasks.task_time_limit", "90", "json")
    _put(db_url, "background_tasks.worker_queues", '["gpu"]', "json")
    cfg = load_runner_settings()
    assert cfg.task_time_limit == 90
    assert cfg.worker_queues == ["gpu"]


def test_env_still_seeds_what_the_db_leaves_alone(db_url: str, monkeypatch) -> None:
    monkeypatch.setenv("SM_BG_TASKS_WORKER_QUEUES", "mail")
    assert load_runner_settings().worker_queues == ["mail"]


def test_unreachable_db_falls_back_to_env_settings(monkeypatch, caplog) -> None:
    def boom(*a, **k):
        raise RuntimeError("no database")

    monkeypatch.setattr("background_tasks.worker_settings.settings_for", boom)
    monkeypatch.setenv("SM_BG_TASKS_TASK_TIME_LIMIT", "12")
    cfg = load_runner_settings()
    assert isinstance(cfg, BackgroundTasksSettings)
    assert cfg.task_time_limit == 12
    assert "Could not read background_tasks settings" in caplog.text
