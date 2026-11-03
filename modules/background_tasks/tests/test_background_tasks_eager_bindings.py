"""Eager tasks keep the caller's authority and validate headers (#751, #752)."""

import pytest
from background_tasks import celery_app
from background_tasks import signals as _signals  # noqa: F401 - connects the handlers
from background_tasks import tenant_context as task_context
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.tenant_context import OWNER_HEADER, TENANT_HEADER, stamp_owner
from celery import current_app
from simple_module_db import TenantIsolationError, current_tenant_id, tenant_context
from simple_module_db.listeners import current_user_id


@pytest.fixture
def eager(monkeypatch):
    monkeypatch.setattr(celery_app, "_discover_task_packages", list)
    previous = current_app._get_current_object()
    app = celery_app.build_celery(BackgroundTasksSettings())
    app.conf.update(task_always_eager=True, sm_execution_tracking="off")
    seen = []

    @app.task(name="eager.job")
    def job():
        headers = {}
        stamp_owner(headers)
        seen.append((current_tenant_id.get(), headers.get(OWNER_HEADER)))

    try:
        yield job, seen
    finally:
        previous.set_current()
        app.close()


def test_eager_task_runs_with_the_callers_tenant_and_owner(eager):
    job, seen = eager
    token = current_user_id.set("caller")
    try:
        with tenant_context("tenant-a"):
            job.apply_async()
            job.delay()
            assert current_tenant_id.get() == "tenant-a"
    finally:
        current_user_id.reset(token)
    assert seen == [("tenant-a", "caller"), ("tenant-a", "caller")]


def test_eager_task_refuses_another_tenants_header(eager):
    job, seen = eager
    with tenant_context("tenant-a"), pytest.raises(TenantIsolationError):
        job.apply_async(headers={TENANT_HEADER: "tenant-b"})
    assert seen == []


def test_a_postrun_for_an_outer_task_unwinds_a_stranded_inner_binding():
    def start(task_id, tenant):
        task = type("T", (), {"request": type("R", (), {TENANT_HEADER: tenant})()})()
        task_context.restore_tenant(task_id=task_id, task=task)

    with tenant_context("ambient"):
        start("outer", "tenant-a")
        start("inner", "tenant-b")  # its postrun never arrives
        task_context.release_tenant(task_id="outer")
        assert current_tenant_id.get() == "ambient"
        assert task_context._tokens.get() == ()
