"""Worker tenancy is public and distinguishes unconfigured from single tenant (#685)."""

import pytest
from background_tasks import sync_db


@pytest.fixture(autouse=True)
def reset_worker():
    sync_db.dispose_sync_engine()
    yield
    sync_db.dispose_sync_engine()


def test_worker_tenancy_is_unknown_until_explicitly_configured(monkeypatch):
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite://")
    assert sync_db.worker_tenancy() is None
    sync_db.set_database_url("sqlite://", default_tenant="acme")
    single = sync_db.worker_tenancy()
    assert isinstance(single, sync_db.WorkerTenancy)
    assert single.multi_tenant is False
    assert single.default_tenant == "acme"

    sync_db.set_database_url("sqlite://", tenant_strict=True, default_tenant="ignored")
    multi = sync_db.worker_tenancy()
    assert multi.multi_tenant is True
    assert multi.default_tenant is None
    assert single.default_tenant == "acme"  # callers hold a snapshot

    sync_db.set_database_url(None)
    assert sync_db.worker_tenancy() is None
    sync_db.set_database_url("sqlite://")
    assert sync_db.worker_tenancy().multi_tenant is False
    assert sync_db.worker_tenancy().default_tenant is None
    sync_db.dispose_sync_engine()
    assert sync_db.worker_tenancy() is None
