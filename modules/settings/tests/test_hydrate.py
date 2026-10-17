"""Tests for hydrate_settings — resolve DB overrides into a BaseSettings instance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from settings.hydrate import hydrate_settings, value_type_for_field
from settings.service import SettingService
from settings.store import SettingsStore


class _Cfg(BaseSettings):
    # Namespaced so a stray ``HOST``/``PORT`` in the runner's env can't win.
    model_config = SettingsConfigDict(env_prefix="SM_TEST_HYDRATE_")

    allow: bool = False
    port: int = 25
    host: str = "localhost"
    tags: list[str] = ["a"]
    rate: float = 1.5


@pytest.mark.asyncio
async def test_hydrate_returns_defaults_when_no_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg == _Cfg()


@pytest.mark.asyncio
async def test_hydrate_applies_scalar_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "allow", "true", "bool")
    await store.set_override("demo", "port", "587", "int")
    await store.set_override("demo", "host", "mail.example.com", "string")
    await store.set_override("demo", "rate", "2.5", "float")

    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.allow is True
    assert cfg.port == 587
    assert cfg.host == "mail.example.com"
    assert cfg.rate == 2.5


@pytest.mark.asyncio
async def test_hydrate_applies_json_list_override(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "tags", '["x","y","z"]', "json")
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.tags == ["x", "y", "z"]


@pytest.mark.asyncio
async def test_hydrate_raises_on_pydantic_validation_error(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    # Stored as json (valid JSON), but a list can't coerce to int → pydantic rejects.
    await store.set_override("demo", "port", "[1,2,3]", "json")
    with pytest.raises(ValidationError):
        await hydrate_settings(_Cfg, store, package="demo")


def test_value_type_for_bool_int_float_str_list() -> None:
    assert value_type_for_field(_Cfg, "allow") == "bool"
    assert value_type_for_field(_Cfg, "port") == "int"
    assert value_type_for_field(_Cfg, "rate") == "float"
    assert value_type_for_field(_Cfg, "host") == "string"
    assert value_type_for_field(_Cfg, "tags") == "json"


def test_hydrate_sync_matches_async_parsing(tmp_path) -> None:
    from settings.hydrate import hydrate_settings_sync
    from settings.models import Setting
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Setting.metadata.create_all(engine)
    with Session(engine) as session:
        for k, v, t in [
            ("demo.port", "587", "int"),
            ("demo.allow", "true", "bool"),
            ("demo.tags", '["x","y"]', "json"),
            ("demo.unknown", "1", "int"),
            ("demo.a.b", "1", "int"),
            ("other.port", "1", "int"),
        ]:
            session.add(Setting(key=k, value=v, value_type=t))
        session.add(
            Setting(scope="user", scope_id="7", key="demo.host", value="no", value_type="string")
        )
        session.commit()
        cfg = hydrate_settings_sync(_Cfg, session, "demo")
    assert (cfg.port, cfg.allow, cfg.tags, cfg.host) == (587, True, ["x", "y"], "localhost")


@pytest.mark.asyncio
async def test_lenient_hydrate_ignores_only_the_invalid_field(db_session, caplog) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "port", "[1,2,3]", "json")
    await store.set_override("demo", "host", "mail.example.com", "string")
    with caplog.at_level("ERROR"):
        cfg = await hydrate_settings(_Cfg, store, package="demo", lenient=True)
    assert cfg.port == 25
    assert cfg.host == "mail.example.com"
    assert "port" in caplog.text


class _Guarded(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_TEST_GUARDED_")

    broker: str = "redis://redis:6379"
    token: str = "ok"
    prod: bool = False

    @field_validator("token")
    @classmethod
    def _token(cls, v: str) -> str:
        if v.startswith("bad"):
            raise ValueError(f"rejected {v}")
        return v

    @model_validator(mode="after")
    def _no_local_broker_in_prod(self):
        if self.prod and "localhost" in self.broker:
            raise ValueError("localhost broker in prod")
        return self


@pytest.mark.asyncio
async def test_lenient_model_level_error_still_raises(db_session) -> None:
    """A cross-field (empty ``loc``) failure keeps the whole-module behaviour."""
    store = SettingsStore(SettingService(db_session))
    await store.set_override("g", "prod", "true", "bool")
    await store.set_override("g", "broker", "redis://localhost:6379", "string")
    with pytest.raises(ValidationError):
        await hydrate_settings(_Guarded, store, package="g", lenient=True)


@pytest.mark.asyncio
async def test_lenient_log_never_echoes_the_stored_value(db_session, caplog) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("g", "token", "bad-s3cr3t", "string")
    with caplog.at_level("ERROR"):
        cfg = await hydrate_settings(_Guarded, store, package="g", lenient=True)
    assert cfg.token == "ok"
    assert "token" in caplog.text
    assert "s3cr3t" not in caplog.text


@pytest.mark.asyncio
async def test_lenient_dropping_a_field_cannot_bypass_a_cross_field_check(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("g", "token", "bad", "string")
    await store.set_override("g", "prod", "true", "bool")
    await store.set_override("g", "broker", "redis://localhost:6379", "string")
    with pytest.raises(ValidationError):
        await hydrate_settings(_Guarded, store, package="g", lenient=True)


@pytest.mark.asyncio
async def test_env_var_beats_a_stored_override(db_session, monkeypatch) -> None:
    """env → DB → default (GH #486): init kwargs outrank pydantic's env source,
    so the hydrator must drop the stored row rather than pass it in."""
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "port", "587", "int")
    await store.set_override("demo", "host", "db.example.com", "string")
    monkeypatch.setenv("SM_TEST_HYDRATE_PORT", "2525")
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.port == 2525
    assert cfg.host == "db.example.com"


def test_env_beats_db_for_sync_hydration(tmp_path, monkeypatch) -> None:
    from settings.hydrate import hydrate_settings_sync
    from settings.models import Setting
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Setting.metadata.create_all(engine)
    monkeypatch.setenv("SM_TEST_HYDRATE_ALLOW", "false")
    with Session(engine) as session:
        session.add(Setting(key="demo.allow", value="true", value_type="bool"))
        session.commit()
        assert hydrate_settings_sync(_Cfg, session, "demo").allow is False


@pytest.mark.asyncio
async def test_db_backed_settings_ignore_env_and_keep_db(db_session, monkeypatch) -> None:
    """``DbBackedSettings`` has no env source, so a same-named var changes nothing."""
    from simple_module_core.settings_base import DbBackedSettings

    class _Db(DbBackedSettings):
        model_config = SettingsConfigDict(env_prefix="SM_TEST_DBB_")
        port: int = 25

    store = SettingsStore(SettingService(db_session))
    await store.set_override("dbb", "port", "587", "int")
    monkeypatch.setenv("SM_TEST_DBB_PORT", "2525")
    monkeypatch.setenv("PORT", "2525")
    assert (await hydrate_settings(_Db, store, package="dbb")).port == 587


@pytest.mark.asyncio
async def test_env_wins_even_where_env_alone_fails_validation(db_session, monkeypatch) -> None:
    """Detecting env-set fields must not construct the env-only view: here it
    would trip the cross-field check that the merged view passes."""
    store = SettingsStore(SettingService(db_session))
    await store.set_override("g", "broker", "redis://redis:6379", "string")
    monkeypatch.setenv("SM_TEST_GUARDED_PROD", "true")
    monkeypatch.setenv("SM_TEST_GUARDED_TOKEN", "from-env")
    await store.set_override("g", "token", "from-db", "string")
    cfg = await hydrate_settings(_Guarded, store, package="g")
    assert (cfg.prod, cfg.token) == (True, "from-env")


@pytest.mark.asyncio
async def test_background_tasks_env_var_beats_stored_override(db_session, monkeypatch) -> None:
    """The bundled class the bug was real for: ``SM_BG_TASKS_*`` must win."""
    from background_tasks.settings import BackgroundTasksSettings

    store = SettingsStore(SettingService(db_session))
    await store.set_override("background_tasks", "task_default_queue", "from-db", "string")
    await store.set_override("background_tasks", "worker_concurrency", "4", "int")
    monkeypatch.setenv("SM_BG_TASKS_TASK_DEFAULT_QUEUE", "from-env")
    cfg = await hydrate_settings(BackgroundTasksSettings, store, package="background_tasks")
    assert cfg.task_default_queue == "from-env"
    assert cfg.worker_concurrency == 4
