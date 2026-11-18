"""Eager workers must use the app's tenancy, provider and permission context."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from background_tasks.core._lifecycle import install_durable_transport
from background_tasks.core.settings import BackgroundTasksSettings
from background_tasks.outbox import worker
from background_tasks.worker import principals
from simple_module_core.events import EventBus
from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.user_directory import DirectoryUser
from simple_module_db import init_db, principal_for


async def test_eager_app_registry_overrides_independently_merged_defaults(settings, monkeypatch):
    for name in ("_host_settings", "_app_registry", "_revision"):
        monkeypatch.setattr(principals, name, getattr(principals, name))
    monkeypatch.setattr(worker, "_bus_override", worker._bus_override)
    state = init_db("sqlite+aiosqlite:///:memory:")
    registry = PrincipalRegistry(multi_tenant=True)
    registry.directory.get_many = AsyncMock(
        return_value={"u1": DirectoryUser("u1", "eager@example.com")}
    )
    registry.permissions.map_role("app-role", ["test.app"])
    state.session_factory.configure(info={PRINCIPALS_KEY: registry})
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(settings=settings, event_bus=EventBus(), db=state),
            background_tasks=SimpleNamespace(
                settings=BackgroundTasksSettings(),
                celery=SimpleNamespace(conf=SimpleNamespace(task_always_eager=True)),
            ),
        )
    )
    monkeypatch.setattr("background_tasks.outbox.sweep.start_sweep", lambda *a: None)
    principals.configure_principals(settings.model_copy(update={"multi_tenant": False}))
    previous = principals.principal_revision()
    install_durable_transport(app)
    assert principals.worker_principal_registry() is registry
    assert principals.worker_principal_registry().multi_tenant
    assert principals.principal_revision() != previous

    cache = {}
    monkeypatch.setattr(worker, "worker_loop_cache", lambda: cache)
    monkeypatch.setattr(worker, "init_db", lambda *a, **kw: state)
    first = worker.worker_session_factory()
    assert first.kw["info"][PRINCIPALS_KEY] is registry
    async with first() as db:
        assert await principal_for(db, "u1", "nonmember") is None
    replacement = PrincipalRegistry(multi_tenant=False, default_tenant="single")
    principals.use_principal_registry(replacement)
    monkeypatch.setattr(worker, "_dispose_soon", lambda *a: None)
    try:
        second = worker.worker_session_factory()
        assert second.kw["info"][PRINCIPALS_KEY] is replacement
        principals.configure_principals(None)
        assert principals._app_registry is None
    finally:
        await state.engine.dispose()
