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
    assert load_runner_settings().task_time_limit == 90


@pytest.mark.parametrize(
    ("field", "stored"),
    [
        ("worker_queues", '["gpu"]'),
        ("include_modules", '["evil"]'),
        ("exclude_modules", '["users"]'),
        ("celery_overrides", '{"task_serializer": "pickle"}'),
    ],
)
def test_env_only_fields_ignore_a_db_value(db_url: str, field: str, stored: str) -> None:
    _put(db_url, f"background_tasks.{field}", stored, "json")
    cfg = load_runner_settings()
    assert field not in BackgroundTasksSettings.model_fields
    assert not hasattr(cfg, field)


@pytest.mark.parametrize(
    ("field", "stored"),
    [
        ("broker_url", '"mod.Transport://x"'),
        ("result_backend", '"pkg.mod:Backend"'),
    ],
)
def test_db_url_naming_an_importable_scheme_is_refused(
    db_url: str, field: str, stored: str, caplog
) -> None:
    _put(db_url, f"background_tasks.{field}", stored, "json")
    cfg = load_runner_settings()  # that field falls back to env/default, loudly
    assert "." not in getattr(cfg, field).split("://")[0]
    assert f"Ignoring stored value for BackgroundTasksSettings.{field}" in caplog.text


def test_unreachable_db_falls_back_to_env_settings(monkeypatch, caplog) -> None:
    def boom(*a, **k):
        raise RuntimeError("no database")

    monkeypatch.setattr("background_tasks.worker_settings.settings_for", boom)
    monkeypatch.setenv("SM_BG_TASKS_TASK_TIME_LIMIT", "12")
    cfg = load_runner_settings()
    assert isinstance(cfg, BackgroundTasksSettings)
    assert cfg.task_time_limit == 12
    assert "Could not read background_tasks settings" in caplog.text


def test_stored_invalid_task_routes_do_not_stop_the_worker(db_url: str, caplog) -> None:
    _put(db_url, "background_tasks.task_routes_override", '{"x": 5}', "json")
    _put(db_url, "background_tasks.task_time_limit", "90", "json")
    with caplog.at_level("ERROR"):
        cfg = load_runner_settings()
    assert cfg.task_routes_override == {}
    assert cfg.task_time_limit == 90  # the module's other overrides survive
    assert "task_routes_override" in caplog.text
