"""Opting out of broadcasting must not require installation identity provisioning."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from background_tasks.core.settings import BackgroundTasksSettings
from background_tasks.worker.runner import build_runner_celery


@pytest.mark.parametrize("channel", [None, "explicit-channel"])
def test_disabled_broadcasting_never_looks_up_identity(monkeypatch, channel):
    settings = BackgroundTasksSettings(broadcast_invalidations=False, invalidation_channel=channel)
    host = SimpleNamespace(multi_tenant=False, default_tenant=None, database_url="unavailable")
    monkeypatch.setattr("background_tasks.worker.runner._load_env", lambda *a: None)
    monkeypatch.setattr("simple_module_hosting.merge_host_settings", lambda: host)
    for target in (
        "background_tasks.worker.principals.configure_principals",
        "background_tasks.core.sync_db.set_database_url",
        "background_tasks.core.sync_db.configure_database",
        "background_tasks.executions.tenant_context.set_default_tenant",
        "simple_module_hosting.leases.configure_process_leases",
        "background_tasks.logs.sink.install_log_sink",
    ):
        monkeypatch.setattr(target, lambda *a, **kw: None)
    monkeypatch.setattr("background_tasks.core.db_settings.worker_database_options", lambda *a: {})
    monkeypatch.setattr("background_tasks.worker.settings.load_runner_settings", lambda: settings)
    lookup = Mock(side_effect=RuntimeError("identity DB unavailable"))
    monkeypatch.setattr("simple_module_hosting.installation.load_installation_id", lookup)
    celery = SimpleNamespace(conf=SimpleNamespace())
    monkeypatch.setattr("background_tasks.worker.celery_app.build_celery", lambda cfg: celery)
    host.redis_url = None

    assert build_runner_celery() is celery
    lookup.assert_not_called()
    assert settings.invalidation_channel == channel
