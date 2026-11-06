"""Tenant validation must abort real broker publication (#752)."""

from queue import Empty
from uuid import uuid4

import pytest
from background_tasks.core.settings import BackgroundTasksSettings
from background_tasks.executions.tenant_context import TENANT_HEADER
from background_tasks.worker import celery_app
from celery import current_app
from simple_module_db import TenantIsolationError, tenant_context


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.setattr(celery_app, "_discover_task_packages", list)
    previous = current_app._get_current_object()
    app = celery_app.build_celery(BackgroundTasksSettings())
    app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_default_queue=str(uuid4()),
        sm_execution_tracking="off",
    )

    @app.task(name="publish.job")
    def job():
        pass

    try:
        with app.connection_for_read() as connection:
            queue = connection.SimpleQueue(app.conf.task_default_queue)
            try:
                yield app, job, queue
            finally:
                queue.clear()
                queue.close()
    finally:
        previous.set_current()
        app.close()


@pytest.mark.parametrize("method", ["apply_async", "send_task", "signature", "delay"])
def test_mismatch_raises_before_sending(publisher, method):
    app, job, queue = publisher
    with tenant_context("tenant-a"), pytest.raises(TenantIsolationError):
        if method == "send_task":
            app.send_task(job.name, headers={TENANT_HEADER: "tenant-b"})
        elif method == "signature":
            job.s().set(headers={TENANT_HEADER: "tenant-b"}).apply_async()
        elif method == "delay":
            # delay has no headers option; task defaults supply the explicit header.
            job._get_exec_options()["headers"] = {TENANT_HEADER: "tenant-b"}
            job.delay()
        else:
            job.apply_async(headers={TENANT_HEADER: "tenant-b"})
    with pytest.raises(Empty):
        queue.get(block=False)


@pytest.mark.parametrize("headers", [{}, {TENANT_HEADER: "tenant-a"}])
@pytest.mark.parametrize("method", ["apply_async", "send_task"])
def test_matching_or_absent_headers_publish_and_stamp(publisher, headers, method):
    app, job, queue = publisher
    with tenant_context("tenant-a"):
        if method == "send_task":
            result = app.send_task(job.name, headers=dict(headers))
        else:
            result = job.apply_async(headers=dict(headers))
    message = queue.get(block=False)
    assert message.headers[TENANT_HEADER] == "tenant-a"
    assert message.headers["id"] == result.id
    message.ack()
