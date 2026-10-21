"""The worker/beat process hydrates DB-backed settings at boot (GH #447-#450 follow-up)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.worker_settings import clear_settings_cache, load_runner_settings
from simple_module_db.stored_settings import Setting
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


def test_worker_boots_on_its_db_config(db_url: str, monkeypatch) -> None:
    """An env-pinned hard limit beside a stored soft limit at or above it (#548):
    the stored soft limit is dropped instead of the worker refusing to start."""
    monkeypatch.setenv("SM_BG_TASKS_TASK_TIME_LIMIT", "50")
    _put(db_url, "background_tasks.task_soft_time_limit", "100", "int")
    _put(db_url, "background_tasks.max_retries", "7", "int")

    cfg = load_runner_settings()

    assert (cfg.task_time_limit, cfg.task_soft_time_limit, cfg.max_retries) == (50, None, 7)


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


def test_shared_runner_builds_celery_from_db_settings(db_url, tmp_path, monkeypatch) -> None:
    """GH #490: the entry point scaffolded apps use must hydrate from the DB."""
    from background_tasks import tenant_context
    from background_tasks.runner import build_runner_celery

    # The runner sets process-wide state; don't leak it into later tests.
    monkeypatch.setattr(tenant_context, "_default_tenant", tenant_context._default_tenant)
    for name in ("_tenant_strict", "_default_tenant"):
        monkeypatch.setattr(sync_db, name, getattr(sync_db, name))
    _put(db_url, "background_tasks.task_default_queue", "from-db", "string")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SM_DATABASE_URL", db_url.replace("sqlite://", "sqlite+aiosqlite://"))
    monkeypatch.delenv("SM_BG_TASKS_TASK_DEFAULT_QUEUE", raising=False)

    celery = build_runner_celery()

    assert celery.conf.task_default_queue == "from-db"


def _forget_after_test(monkeypatch, *names: str) -> None:
    """Unset ``names`` now and again at teardown, even if the code under test sets them."""
    for name in names:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def test_fallback_env_file_is_adopted_as_the_project_root(tmp_path, monkeypatch) -> None:
    """Launched from inside some other checkout, the walk-up stops at *its*
    missing ``.env``; the script-relative file must still win, and the sqlite
    anchor must follow it rather than the cwd (GH #490 review)."""
    from background_tasks.runner import _load_env
    from simple_module_hosting.bootstrap_settings import BootstrapSettings

    app = tmp_path / "app"
    app.mkdir()
    (app / ".env").write_text(
        "SM_DATABASE_URL=sqlite+aiosqlite:///./app.db\nSM_TEST_RUNNER_MARKER=loaded\n"
    )
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    monkeypatch.chdir(other)
    _forget_after_test(monkeypatch, "SM_PROJECT_ROOT", "SM_DATABASE_URL", "SM_TEST_RUNNER_MARKER")

    _load_env(app / ".env")

    assert os.environ["SM_PROJECT_ROOT"] == str(app)
    assert os.environ["SM_TEST_RUNNER_MARKER"] == "loaded"
    assert BootstrapSettings().database_url == f"sqlite+aiosqlite:///{(app / 'app.db').resolve()}"


def test_explicit_project_root_is_never_overridden(tmp_path, monkeypatch) -> None:
    from background_tasks.runner import _load_env

    app = tmp_path / "app"
    app.mkdir()
    (app / ".env").write_text("SM_TEST_RUNNER_MARKER=fallback\n")
    _forget_after_test(monkeypatch, "SM_TEST_RUNNER_MARKER")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path / "chosen"))

    _load_env(app / ".env")

    assert os.environ["SM_PROJECT_ROOT"] == str(tmp_path / "chosen")
    assert "SM_TEST_RUNNER_MARKER" not in os.environ
