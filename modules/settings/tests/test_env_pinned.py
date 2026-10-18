"""Writes and labels agree with env → DB → default (GH #486, PR review).

Hydration drops a stored override for a field the environment supplies, so
the editor must refuse to store one (it would only ever take effect in the
process that saved it) and must label the field "env" by the same rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from settings.registration import register_module_settings
from settings.reload import EnvPinnedError, apply_changes_and_reload
from settings.service import SettingService
from settings.services import SettingsServices
from settings.settings import SettingsSettings
from settings.store import SettingsStore
from simple_module_core.events import EventBus


class _Cfg(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_TEST_PINNED_")

    queue: str = "default"
    api_key: SecretStr = SecretStr("")


@dataclass
class _Services:
    settings: _Cfg


@pytest.fixture
def pinned_app(db_session) -> FastAPI:
    app = FastAPI()
    app.state.settings = SettingsServices(settings=SettingsSettings())
    register_module_settings(app, "pinned", _Cfg, lambda s: _Services(settings=s))
    return app


async def test_saving_an_env_set_field_is_refused(pinned_app, db_session, monkeypatch):
    app = pinned_app
    monkeypatch.setenv("SM_TEST_PINNED_QUEUE", "from-env")
    store = SettingsStore(SettingService(db_session))
    before = app.state.pinned.settings

    with pytest.raises(EnvPinnedError) as exc:
        await apply_changes_and_reload(
            app, EventBus(), store, package="pinned", changes={"queue": "from-db"}
        )

    assert exc.value.fields == ["queue"]
    assert app.state.pinned.settings is before
    assert await store.get_overrides("pinned") == {}


async def test_a_secret_is_stored_as_submitted_not_as_its_dump(pinned_app, db_session):
    app = pinned_app
    """``SecretStr`` dumps as asterisks; that must never reach the store."""
    store = SettingsStore(SettingService(db_session))
    await apply_changes_and_reload(
        app, EventBus(), store, package="pinned", changes={"api_key": "s3cr3t"}
    )
    raw, _ = (await store.get_overrides("pinned"))["api_key"]
    assert raw == "s3cr3t"


def test_a_secrets_file_value_is_labelled_env(tmp_path):
    """Not in ``os.environ``, but hydration still lets it win — so must the label."""
    from settings._module_settings import _field_view

    (tmp_path / "SM_TEST_PINNED_QUEUE").write_text("from-secret")

    class _WithSecrets(_Cfg):
        model_config = SettingsConfigDict(env_prefix="SM_TEST_PINNED_", secrets_dir=str(tmp_path))

    view = _field_view("queue", _WithSecrets(), "SM_PINNED_", frozenset({"queue"}))
    assert view.env_set is True
    assert view.source == "env"


async def test_editor_put_answers_422_on_the_field(authenticated_client, monkeypatch):
    monkeypatch.setenv("SM_BG_TASKS_TASK_DEFAULT_QUEUE", "from-env")
    resp = await authenticated_client.put(
        "/api/settings/modules/background_tasks", json={"task_default_queue": "from-db"}
    )
    assert resp.status_code == 422, resp.text
    (error,) = resp.json()["detail"]
    assert error["loc"][-1] == "task_default_queue"
    assert error["type"] == "env_pinned"
    assert error["msg"].startswith("Set by an environment variable")


async def test_saving_a_broker_url_seeded_by_redis_url_is_refused(
    authenticated_client, monkeypatch
):
    """``SM_REDIS_URL`` reaches the field through a default factory, not an env
    source, but it still wins, so the editor must not store a dead value."""
    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")
    resp = await authenticated_client.put(
        "/api/settings/modules/background_tasks", json={"broker_url": "redis://db:6379/0"}
    )
    assert resp.status_code == 422, resp.text
    assert {e["loc"][-1] for e in resp.json()["detail"]} == {"broker_url"}
