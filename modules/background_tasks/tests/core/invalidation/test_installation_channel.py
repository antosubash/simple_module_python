"""Resolve channels at the web and Celery entry points, without a Redis server."""

from types import SimpleNamespace

import pytest
from background_tasks.core._lifecycle import start_invalidation_transport
from background_tasks.core.settings import BackgroundTasksSettings
from simple_module_core.eventing.invalidation import InvalidationBus
from simple_module_db.queries.stored_settings import Setting
from sqlalchemy import create_engine


@pytest.fixture
def database_url(tmp_path):
    url = f"sqlite:///{tmp_path / 'identity.db'}"
    engine = create_engine(url)
    Setting.metadata.create_all(engine)
    engine.dispose()
    return url.replace("sqlite://", "sqlite+aiosqlite://")


async def _web_channel(database_url, monkeypatch, settings=None):
    made = []

    class Transport:
        def __init__(self, bus, url, channel, **kwargs):
            made.append((channel, kwargs))

        async def start(self):
            pass

    monkeypatch.setattr("background_tasks.core.invalidation.RedisInvalidationTransport", Transport)
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(
                settings=SimpleNamespace(database_url=database_url), invalidation=InvalidationBus()
            ),
            background_tasks=SimpleNamespace(
                settings=settings or BackgroundTasksSettings(broadcast_invalidations=True),
                invalidation_transport=None,
            ),
        )
    )
    await start_invalidation_transport(app)
    return made


async def test_web_uses_database_identity_and_bridges_legacy(database_url, monkeypatch):
    from simple_module_hosting.installation import load_installation_id

    monkeypatch.delenv("SM_BG_TASKS_INVALIDATION_CHANNEL", raising=False)
    channel, options = (await _web_channel(database_url, monkeypatch))[0]
    assert channel == f"simple_module.invalidation.{load_installation_id(database_url)}"
    assert options == {"legacy_channel": "simple_module.invalidation"}


async def test_explicit_env_channel_beats_stored_channel(database_url, monkeypatch):
    from simple_module_db.queries.stored_settings import hydrate_settings_sync
    from sqlalchemy.orm import Session

    engine = create_engine(database_url.replace("sqlite+aiosqlite://", "sqlite://"))
    with Session(engine) as session:
        session.add(Setting(key="background_tasks.invalidation_channel", value="db-channel"))
        session.commit()
        monkeypatch.setenv("SM_BG_TASKS_INVALIDATION_CHANNEL", "env-channel")
        settings = hydrate_settings_sync(BackgroundTasksSettings, session, "background_tasks")
    engine.dispose()
    settings.broadcast_invalidations = True
    assert await _web_channel(database_url, monkeypatch, settings) == [
        ("env-channel", {"legacy_channel": None})
    ]


async def test_before_migrations_no_shared_fallback_channel(tmp_path, monkeypatch):
    monkeypatch.delenv("SM_BG_TASKS_INVALIDATION_CHANNEL", raising=False)
    url = f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}"
    with pytest.raises(RuntimeError, match="awaits settings table migrations"):
        await _web_channel(url, monkeypatch)
    # Setup creates the settings table; replaying the hook now provisions a shared channel.
    engine = create_engine(url.replace("sqlite+aiosqlite://", "sqlite://"))
    Setting.metadata.create_all(engine)
    engine.dispose()
    assert len(await _web_channel(url, monkeypatch)) == 1


async def test_separate_installations_resolve_separate_channels(
    database_url, tmp_path, monkeypatch
):
    monkeypatch.delenv("SM_BG_TASKS_INVALIDATION_CHANNEL", raising=False)
    other_url = f"sqlite:///{tmp_path / 'other.db'}"
    engine = create_engine(other_url)
    Setting.metadata.create_all(engine)
    engine.dispose()
    first = await _web_channel(database_url, monkeypatch)
    second = await _web_channel(other_url.replace("sqlite://", "sqlite+aiosqlite://"), monkeypatch)
    assert first[0][0] != second[0][0]
