"""Worker-side signals stamp the message's tenant themselves (#371).

The publish signal fires in the publisher's process and may never have
written the row (another DB, or a publisher with no ``background_tasks``
loaded), so prerun and the terminal handlers carry the header's tenant into
the upsert — and never blank one already stamped.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

from background_tasks import sync_db
from background_tasks.models import TaskExecution
from background_tasks.signals import (
    on_task_failure,
    on_task_postrun,
    on_task_prerun,
    on_task_publish,
    on_task_retry,
    on_task_revoked,
    on_task_success,
)
from background_tasks.tenant_context import TENANT_HEADER
from simple_module_db import tenant_context
from sqlalchemy import select


def _tenant_of(task_id: str) -> str | None:
    with sync_db.get_sync_session_factory()() as session:
        return session.execute(
            select(TaskExecution.tenant_id).where(TaskExecution.celery_task_id == task_id)
        ).scalar_one()


def _task(tenant: str | None, task_id: str | None = None) -> SimpleNamespace:
    headers = {TENANT_HEADER: tenant} if tenant else {}
    return SimpleNamespace(name="demo.echo", request=SimpleNamespace(id=task_id, **headers))


def _run(task_id: str, tenant: str | None) -> None:
    task = _task(tenant, task_id)
    on_task_prerun(sender=task, task_id=task_id, task=task)
    on_task_postrun(sender=task, task_id=task_id, task=task)


def test_prerun_creates_the_row_with_the_header_tenant(sync_sqlite: Path):
    task_id = str(uuid.uuid4())
    task = _task("acme", task_id)
    on_task_prerun(sender=task, task_id=task_id, task=task)
    try:
        assert _tenant_of(task_id) == "acme"
    finally:
        on_task_postrun(sender=task, task_id=task_id, task=task)


def test_success_and_failure_stamp_a_row_they_create(sync_sqlite: Path):
    ok_id, failed_id = str(uuid.uuid4()), str(uuid.uuid4())
    on_task_success(sender=_task("globex", ok_id), result=None)
    on_task_failure(sender=_task("globex"), task_id=failed_id, exception=RuntimeError("x"))
    assert _tenant_of(ok_id) == "globex"
    assert _tenant_of(failed_id) == "globex"


def test_retry_and_revoke_read_the_request_header(sync_sqlite: Path):
    retry_id, revoked_id = str(uuid.uuid4()), str(uuid.uuid4())
    on_task_retry(
        sender=_task(None),
        request=SimpleNamespace(id=retry_id, retries=1, **{TENANT_HEADER: "acme"}),
    )
    # A worker ``Request`` keeps its headers in ``request_dict``.
    on_task_revoked(
        sender=_task(None),
        request=SimpleNamespace(id=revoked_id, request_dict={TENANT_HEADER: "acme"}),
    )
    assert _tenant_of(retry_id) == "acme"
    assert _tenant_of(revoked_id) == "acme"


def test_a_headerless_signal_never_blanks_a_stamp(sync_sqlite: Path):
    task_id = str(uuid.uuid4())
    with tenant_context("acme"):
        on_task_publish(
            sender="demo.echo", headers={"id": task_id, "task": "demo.echo"}, body=([], {}, {})
        )
    _run(task_id, None)
    assert _tenant_of(task_id) == "acme"


def test_a_platform_message_stays_a_platform_row_on_a_default_tenant_install(
    sync_sqlite: Path,
):
    # The default tenant is what the body *binds*, not what the row records.
    sync_db.set_database_url(sync_db._resolve_url(), default_tenant="main")
    task_id = str(uuid.uuid4())
    _run(task_id, None)
    assert _tenant_of(task_id) is None
