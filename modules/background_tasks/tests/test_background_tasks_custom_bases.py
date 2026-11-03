"""Custom task bases retain publish validation, including eager runs (#765)."""

from uuid import uuid4

import pytest
from background_tasks import signals as _signals  # noqa: F401 - connects the handlers
from background_tasks.tenant_celery import TenantCelery, TenantTask
from background_tasks.tenant_context import OWNER_HEADER, TENANT_HEADER
from celery import Task, _state, current_app, shared_task
from simple_module_db import TenantIsolationError, current_tenant_id, tenant_context
from simple_module_db.listeners import current_user_id


class CustomTask(Task):
    """A module's ordinary Celery extension point."""


@pytest.fixture
def celery_app(monkeypatch):
    # Task decorators register callbacks for future apps; keep them test-local.
    monkeypatch.setattr(_state, "_on_app_finalizers", set(_state._on_app_finalizers))
    previous = current_app._get_current_object()
    app = TenantCelery("custom-bases", broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=True, sm_execution_tracking="off")
    try:
        yield app
    finally:
        previous.set_current()
        app.close()


@pytest.fixture(params=["app", "shared"])
def register(celery_app, request):
    decorator = celery_app.task if request.param == "app" else shared_task

    def create(base=CustomTask):
        @decorator(name=f"custom-bases.{uuid4()}", base=base, bind=True)
        def job(self):
            return current_tenant_id.get(), self.request.headers

        # Resolve Celery's lazy proxy so registration errors surface here.
        return job._get_current_object() if hasattr(job, "_get_current_object") else job

    return create


@pytest.mark.parametrize("eager", [True, False])
@pytest.mark.parametrize("base", [CustomTask, TenantTask])
def test_custom_and_default_bases_reject_mismatching_headers(celery_app, register, eager, base):
    job = register(base)
    celery_app.conf.task_always_eager = eager
    with tenant_context("tenant-a"):
        with pytest.raises(TenantIsolationError):
            job.apply_async(headers={TENANT_HEADER: "tenant-b"})
        assert current_tenant_id.get() == "tenant-a"


def test_custom_base_eager_stamps_caller_and_merges_default_headers(register):
    job = register()
    job._get_exec_options()["headers"] = {"default": "kept", "override": "old"}
    token = current_user_id.set("caller")
    try:
        with tenant_context("tenant-a"):
            result = job.apply_async(headers={"override": "new"}).get()
            assert current_tenant_id.get() == "tenant-a"
    finally:
        current_user_id.reset(token)
    assert result == (
        "tenant-a",
        {
            "default": "kept",
            "override": "new",
            TENANT_HEADER: "tenant-a",
            OWNER_HEADER: "caller",
        },
    )


def test_custom_apply_async_override_runs_after_validation(register):
    calls = []

    class OverridingTask(Task):
        def apply_async(self, *args, **kwargs):
            calls.append(kwargs["headers"].copy())
            return super().apply_async(*args, **kwargs)

    job = register(OverridingTask)
    with tenant_context("tenant-a"):
        with pytest.raises(TenantIsolationError):
            job.apply_async(headers={TENANT_HEADER: "tenant-b"})
        assert calls == []
        assert job.apply_async().get()[0] == "tenant-a"
    assert calls == [{TENANT_HEADER: "tenant-a"}]


def test_incompatible_custom_base_fails_clearly_at_registration(register):
    class SingleBaseMeta(type):
        def __new__(mcls, name, bases, namespace):
            if len(bases) > 1:
                raise TypeError("multiple inheritance refused")
            return super().__new__(mcls, name, bases, namespace)

    class IncompatibleTask(Task, metaclass=SingleBaseMeta):
        pass

    with pytest.raises(
        TypeError, match=r"Cannot compose tenant publish validation.*IncompatibleTask"
    ):
        register(IncompatibleTask)
