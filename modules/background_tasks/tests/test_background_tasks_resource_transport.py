"""Resource references survive worker-only tracking and administrative retries."""

from types import SimpleNamespace

import pytest
from background_tasks import sync_db
from background_tasks.models import TaskExecution
from background_tasks.signals import on_task_failure, on_task_publish
from sqlalchemy import select


@pytest.mark.parametrize("mode", ["full", "terminal", "failures"])
def test_worker_only_terminal_creation_keeps_resource(mode, sync_sqlite):
    task = SimpleNamespace(
        name="demo.image",
        request=SimpleNamespace(
            id="terminal-resource",
            headers={
                "sm_tracking": mode,
                "sm_resource_type": "demo.image",
                "sm_resource_id": "7",
                "sm_owner_id": "owner",
                "sm_tenant_id": "org",
            },
            args=[7],
            kwargs={"format": "png"},
            delivery_info={"routing_key": "images"},
        ),
    )
    on_task_failure(sender=task, task_id=task.request.id, exception=ValueError("bad image"))
    with sync_db.get_sync_session_factory()() as db:
        row = db.execute(select(TaskExecution)).scalar_one()
        assert (row.resource_type, row.resource_id) == ("demo.image", "7")
        assert (row.owner_user_id, row.tenant_id, row.queue) == ("owner", "org", "images")
        assert (row.args, row.kwargs) == ([7], {"format": "png"})


@pytest.mark.parametrize(
    "headers",
    [
        {"sm_resource_type": "demo.image"},
        {"sm_resource_type": "bad type", "sm_resource_id": "7"},
        {"sm_resource_id": "7"},
    ],
)
def test_invalid_message_resource_grants_no_access(headers, sync_sqlite):
    on_task_publish(sender="demo.image", headers={"id": "invalid-resource", **headers})
    with sync_db.get_sync_session_factory()() as db:
        row = db.execute(select(TaskExecution)).scalar_one()
        assert (row.resource_type, row.resource_id) == (None, None)


@pytest.mark.usefixtures("_stub_celery")
async def test_admin_retry_preserves_resource_in_row_and_message(
    app, seed_execution, execution_rows, authenticated_client
):
    row = await seed_execution(
        resource_type="demo.image", resource_id="7", owner_user_id="owner", tenant_id="org"
    )
    response = await authenticated_client.post(
        f"/api/background_tasks/admin/executions/{row.id}/retry"
    )
    assert response.status_code == 200, response.text
    child = next(item for item in await execution_rows() if item.id != row.id)
    assert (child.resource_type, child.resource_id, child.owner_user_id, child.tenant_id) == (
        "demo.image",
        "7",
        "owner",
        "org",
    )
    assert app.state.background_tasks.celery.send_task.call_args.kwargs["headers"] == {
        "sm_resource_type": "demo.image",
        "sm_resource_id": "7",
    }


def test_resource_pair_is_required_by_database(sync_sqlite):
    from sqlalchemy.exc import IntegrityError

    with sync_db.get_sync_session_factory()() as db:
        db.add(TaskExecution(task_name="demo.image", resource_type="demo.image"))
        with pytest.raises(IntegrityError):
            db.flush()


def test_off_tracking_keeps_owner_tenant_but_never_inherits_resource(monkeypatch):
    from background_tasks import _signal_support
    from background_tasks.signals import on_task_postrun, on_task_prerun
    from background_tasks.tenant_context import stamp_owner, stamp_tenant
    from simple_module_db import current_tenant_id

    def forbidden():
        pytest.fail("OFF tracking opened a session")

    monkeypatch.setattr(_signal_support, "sync_session", forbidden)
    task = SimpleNamespace(
        name="demo.parent",
        request=SimpleNamespace(
            id="off-parent",
            headers={
                "sm_tracking": "off",
                "sm_tenant_id": "org",
                "sm_owner_id": "owner",
                "sm_resource_type": "demo.image",
                "sm_resource_id": "7",
            },
        ),
    )
    before = current_tenant_id.get()
    on_task_prerun(sender=task, task=task, task_id=task.request.id)
    try:
        child = {"id": "off-child", "sm_tracking": "off"}
        on_task_publish(sender="demo.child", headers=child)
        assert child == {
            "id": "off-child",
            "sm_tracking": "off",
            "sm_tenant_id": "org",
            "sm_owner_id": "owner",
        }
    finally:
        on_task_postrun(sender=task, task=task, task_id=task.request.id)
    assert current_tenant_id.get() == before
    headers = {}
    stamp_owner(headers)
    stamp_tenant(headers)
    assert "sm_owner_id" not in headers
