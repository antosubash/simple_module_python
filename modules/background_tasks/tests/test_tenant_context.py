"""The enqueuing request's tenant is restored around the task body."""

from __future__ import annotations

from types import SimpleNamespace

from background_tasks.tenant_context import (
    TENANT_HEADER,
    release_tenant,
    restore_tenant,
    stamp_tenant,
)
from simple_module_db import current_tenant_id, tenant_context


def test_publish_stamps_current_tenant():
    headers: dict = {}
    with tenant_context("acme"):
        stamp_tenant(headers)
    assert headers[TENANT_HEADER] == "acme"


def test_publish_without_tenant_leaves_headers_alone():
    headers: dict = {}
    stamp_tenant(headers)
    assert TENANT_HEADER not in headers


def test_explicit_header_is_not_overwritten():
    headers = {TENANT_HEADER: "chosen"}
    with tenant_context("acme"):
        stamp_tenant(headers)
    assert headers[TENANT_HEADER] == "chosen"


def test_prerun_enters_and_postrun_leaves_the_tenant():
    task = SimpleNamespace(request=SimpleNamespace(**{TENANT_HEADER: "acme"}))
    restore_tenant(task_id="t1", task=task)
    try:
        assert current_tenant_id.get() == "acme"
    finally:
        release_tenant(task_id="t1")
    assert current_tenant_id.get() is None


def test_tenant_read_from_request_headers_dict():
    task = SimpleNamespace(request=SimpleNamespace(headers={TENANT_HEADER: "globex"}))
    restore_tenant(task_id="t2", task=task)
    try:
        assert current_tenant_id.get() == "globex"
    finally:
        release_tenant(task_id="t2")


def test_task_without_tenant_runs_unscoped():
    restore_tenant(task_id="t3", task=SimpleNamespace(request=SimpleNamespace()))
    assert current_tenant_id.get() is None
    release_tenant(task_id="t3")  # no token recorded — must be a no-op
