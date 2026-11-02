"""A real worker database and filesystem, without a Celery broker."""

import pytest
from background_tasks import outbox_worker, sync_db
from background_tasks.worker_settings import clear_settings_cache
from file_storage.models import StoredFile
from simple_module_core.events import EventBus
from simple_module_db.stored_settings import Setting
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def worker_db(tmp_path, monkeypatch):
    outbox_worker.reset_worker_state()
    sync_db.dispose_sync_engine()
    clear_settings_cache()
    monkeypatch.setattr(sync_db, "discover_audit_callback", lambda: None)
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    StoredFile.metadata.create_all(engine)
    Setting.metadata.create_all(engine)
    root = tmp_path / "objects"
    with Session(engine) as db:
        db.add(Setting(key="file_storage.fs_root_path", value=str(root), value_type="string"))
        db.commit()
    sync_db.set_database_url(str(engine.url), tenant_strict=True)
    bus = EventBus()
    outbox_worker.use_bus(bus)
    yield root, engine, bus
    outbox_worker.reset_worker_state()
    sync_db.dispose_sync_engine()
    clear_settings_cache()
    engine.dispose()


def set_setting(engine, name, value, value_type="integer"):
    with Session(engine) as db:
        db.add(Setting(key=f"file_storage.{name}", value=value, value_type=value_type))
        db.commit()
    clear_settings_cache()
