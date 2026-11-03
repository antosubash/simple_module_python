"""Execution-local authority and log bindings (#751)."""

from contextvars import Context
from types import SimpleNamespace

import pytest
from background_tasks import tenant_context as task_context
from background_tasks.log_context import get_log_context
from background_tasks.signals import on_task_postrun, on_task_prerun
from background_tasks.tenant_context import OWNER_HEADER, TENANT_HEADER, stamp_owner
from celery import Celery
from simple_module_db import current_tenant_id, tenant_context
from simple_module_db.listeners import current_user_id


@pytest.fixture
def celery_app():
    with Celery("bindings", broker="memory://", set_as_current=False) as app:
        app.conf.update(sm_execution_tracking="off", task_always_eager=True)
        yield app


def _start(app, task_id, tenant=None, owner=None):
    task = SimpleNamespace(
        app=app,
        name="bindings.job",
        request=SimpleNamespace(headers={TENANT_HEADER: tenant, OWNER_HEADER: owner}),
    )
    on_task_prerun(sender=task, task=task, task_id=task_id, args=[], kwargs={})
    return task


def _finish(task, task_id):
    on_task_postrun(sender=task, task=task, task_id=task_id)


def _binding():
    headers = {}
    stamp_owner(headers)
    return current_tenant_id.get(), headers.get(OWNER_HEADER), get_log_context()


def test_overlapping_uuid_restores_each_context(celery_app):
    first, second = Context(), Context()
    for ctx in (first, second):
        ctx.run(_start, celery_app, "same-id", "tenant-a", "user-a")
    for ctx in (first, second):
        task = SimpleNamespace(app=celery_app, name="bindings.job")
        ctx.run(_finish, task, "same-id")
    assert first.run(_binding) == (None, None, {})
    assert second.run(_binding) == (None, None, {})
    task = second.run(_start, celery_app, "headerless")
    try:
        assert second.run(_binding)[:2] == (None, None)
    finally:
        second.run(_finish, task, "headerless")


@pytest.mark.parametrize("default_tenant", [None, "configured-default"])
def test_headerless_task_clears_ambient_authority(celery_app, monkeypatch, default_tenant):
    monkeypatch.setattr(task_context, "_default_tenant", default_tenant)

    def run():
        user_token = current_user_id.set("ambient-user")
        try:
            with tenant_context("ambient-tenant"):
                task = _start(celery_app, "headerless")
                try:
                    # Never the ambient binding; the configured default when set.
                    assert _binding()[:2] == (default_tenant, None)
                finally:
                    _finish(task, "headerless")
                assert _binding()[:2] == ("ambient-tenant", "ambient-user")
        finally:
            current_user_id.reset(user_token)

    Context().run(run)


@pytest.mark.parametrize(
    "headers", [{}, {TENANT_HEADER: "inner-tenant", OWNER_HEADER: "inner-user"}]
)
def test_nested_eager_same_uuid_restores_outer_binding(celery_app, headers):
    @celery_app.task(name="bindings.inner")
    def inner():
        # In-process: a headerless inner run is its caller's (the outer task's) context.
        expected = ("inner-tenant", "inner-user") if headers else ("outer-tenant", "outer-user")
        assert _binding()[:2] == expected
        return True

    @celery_app.task(name="bindings.outer")
    def outer():
        before = _binding()
        assert inner.apply(
            task_id="same-id",
            headers=headers,
            throw=True,
        ).get()
        assert _binding() == before
        return True

    def run():
        assert outer.apply(
            task_id="same-id",
            headers={TENANT_HEADER: "outer-tenant", OWNER_HEADER: "outer-user"},
            throw=True,
        ).get()
        assert _binding() == (None, None, {})

    Context().run(run)
