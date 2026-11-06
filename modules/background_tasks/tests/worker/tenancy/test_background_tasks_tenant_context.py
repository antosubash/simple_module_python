"""The enqueuing request's tenant is restored around the task body."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from background_tasks.executions.tenant_context import (
    OWNER_HEADER,
    TENANT_HEADER,
    release_tenant,
    restore_tenant,
    stamp_owner,
    stamp_tenant,
)
from simple_module_db import TenantIsolationError, current_tenant_id, tenant_context


def test_publish_stamps_current_tenant():
    headers: dict = {}
    with tenant_context("acme"):
        stamp_tenant(headers)
    assert headers[TENANT_HEADER] == "acme"


def test_publish_without_tenant_leaves_headers_alone():
    headers: dict = {}
    stamp_tenant(headers)
    assert TENANT_HEADER not in headers


def test_platform_code_may_enqueue_for_an_explicit_tenant():
    headers = {TENANT_HEADER: "chosen"}
    stamp_tenant(headers)  # no tenant bound
    assert headers[TENANT_HEADER] == "chosen"


def test_request_code_cannot_enqueue_as_another_tenant():
    with tenant_context("acme"), pytest.raises(TenantIsolationError):
        stamp_tenant({TENANT_HEADER: "other"})


def test_malformed_tenant_on_a_message_is_not_restored():
    task = SimpleNamespace(request=SimpleNamespace(**{TENANT_HEADER: "x" * 300}))
    restore_tenant(task_id="t9", task=task)
    assert current_tenant_id.get() is None
    release_tenant(task_id="t9")


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


def test_headerless_worker_task_enqueues_without_an_owner():
    restore_tenant(task_id="t4", task=SimpleNamespace(request=SimpleNamespace()))
    try:
        headers: dict = {}
        stamp_owner(headers)
        assert OWNER_HEADER not in headers
    finally:
        release_tenant(task_id="t4")


@pytest.mark.parametrize("next_owner", [None, "next-user"])
def test_stranded_prerun_never_reaches_the_next_task(next_owner):
    """#861: a prerun without its postrun must not decide the next task's owner."""
    stale = SimpleNamespace(request=SimpleNamespace(**{OWNER_HEADER: "stale-user"}))
    restore_tenant(task_id="t5", task=stale)  # its postrun never runs
    request = SimpleNamespace(**({OWNER_HEADER: next_owner} if next_owner else {}))
    restore_tenant(task_id="t6", task=SimpleNamespace(request=request))
    try:
        headers: dict = {}
        stamp_owner(headers)
        assert headers.get(OWNER_HEADER) == next_owner
    finally:
        release_tenant(task_id="t6")
        release_tenant(task_id="t5")  # unwinds the stranded binding too
    headers = {}
    stamp_owner(headers)
    assert OWNER_HEADER not in headers
