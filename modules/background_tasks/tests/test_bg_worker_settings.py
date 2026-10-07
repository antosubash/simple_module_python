"""settings_for hydrates DB-backed settings through the worker's sync session."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from background_tasks import sync_db
from background_tasks.worker_settings import clear_settings_cache, settings_for
from pydantic import Field
from settings.models import Setting
from simple_module_core.settings_base import DbBackedSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _Cfg(DbBackedSettings):
    backend: str = "filesystem"
    tags: list[str] = Field(default_factory=list)


@pytest.fixture
def db_url(tmp_path) -> Iterator[str]:
    url = f"sqlite:///{tmp_path / 'w.db'}"
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


def test_settings_for_reads_db_overrides(db_url: str) -> None:
    assert _Cfg().backend == "filesystem"
    _put(db_url, "demo.backend", "s3", "string")
    _put(db_url, "demo.tags", '["a","b"]', "json")
    cfg = settings_for(_Cfg, "demo")
    assert cfg.backend == "s3"
    assert cfg.tags == ["a", "b"]


def test_settings_for_caches_until_ttl_expires(db_url: str) -> None:
    assert settings_for(_Cfg, "demo").backend == "filesystem"
    _put(db_url, "demo.backend", "s3", "string")
    assert settings_for(_Cfg, "demo").backend == "filesystem"  # cached
    assert settings_for(_Cfg, "demo", ttl=0).backend == "s3"
