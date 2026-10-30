"""Task resource grants use filtered policies and stay tenant scoped."""

import pytest
from background_tasks.constants import TaskStatus
from background_tasks.models import TaskExecution
from simple_module_core.resources import ResourceType
from simple_module_core.tenancy import TenantRole
from simple_module_db.resource_policy import select_by_id
from sqlalchemy import false

URL = "/api/background_tasks/tasks/{}/status"


class SharedPolicy:
    allowed = True

    def filter(self, principal, action, stmt):
        return stmt if self.allowed else stmt.where(false())

    def can(self, principal, action, obj):
        return False  # A share is visible through filter(), never can().


async def test_resource_share_revocation_and_tenant_boundary(app, tenant_client, seed_execution):
    policy = SharedPolicy()
    app.state.sm.resource_types.register(
        ResourceType("demo.image", policy, select_by_id(TaskExecution))
    )
    async with (
        tenant_client(TenantRole.MEMBER) as owner,
        tenant_client(TenantRole.MEMBER, tenant_id=owner.tenant_id) as viewer,
        tenant_client(TenantRole.MEMBER) as outsider,
    ):
        resource = await seed_execution(tenant_id=owner.tenant_id)
        task = await seed_execution(
            status=TaskStatus.RUNNING,
            tenant_id=owner.tenant_id,
            owner_user_id=owner.user_id,
            resource_type="demo.image",
            resource_id=str(resource.id),
            traceback="secret",
        )
        response = await viewer.client.get(URL.format(task.celery_task_id))
        assert response.status_code == 200, response.text
        assert (
            not {"args", "traceback", "resource_type", "resource_id", "result"}
            & response.json().keys()
        )
        assert (await outsider.client.get(URL.format(task.celery_task_id))).status_code == 404
        policy.allowed = False
        assert (await viewer.client.get(URL.format(task.celery_task_id))).status_code == 404
        policy.allowed = True
        async with app.state.sm.db.session_factory() as session:
            from sqlalchemy import delete

            await session.execute(delete(TaskExecution).where(TaskExecution.id == resource.id))
            await session.commit()
        assert (await viewer.client.get(URL.format(task.celery_task_id))).status_code == 404


@pytest.mark.parametrize(
    "resource_type,resource_id",
    [
        ("unknown.type", "abc"),
        ("demo.image", "bad-id"),
        ("demo.image", "00000000-0000-0000-0000-000000000000"),
    ],
)
async def test_unavailable_resource_is_the_same_404(
    resource_type, resource_id, app, tenant_client, seed_execution
):
    app.state.sm.resource_types.register(
        ResourceType("demo.image", SharedPolicy(), select_by_id(TaskExecution))
    )
    async with tenant_client(TenantRole.MEMBER) as me:
        task = await seed_execution(
            tenant_id=me.tenant_id, resource_type=resource_type, resource_id=resource_id
        )
        response = await me.client.get(URL.format(task.celery_task_id))
        assert response.status_code == 404
        assert response.json()["detail"] == "Task not found"


@pytest.mark.parametrize("headers", [None, {}, {"custom": "value"}])
def test_resource_signature_is_cloned_and_headers_are_merged(headers):
    from background_tasks import with_task_resource
    from celery import signature

    original = signature("demo.images", headers=headers)
    attached = with_task_resource(original, resource_type="demo.image", resource_id="7")
    assert original.options["headers"] == headers
    assert attached.options["headers"] == {
        **(headers or {}),
        "sm_resource_type": "demo.image",
        "sm_resource_id": "7",
    }


@pytest.mark.parametrize(
    "kind,key",
    [
        ("", "7"),
        ("bad type", "7"),
        ("demo.image", ""),
        ("demo.image", "x" * 256),
        ("demo.image", "x\n"),
        ("demo.image", 7),
    ],
)
def test_resource_headers_are_validated(kind, key):
    from background_tasks import with_task_resource
    from celery import signature

    with pytest.raises(ValueError):
        with_task_resource(signature("demo.images"), resource_type=kind, resource_id=key)


async def test_resource_access_requires_an_active_tenant(app, seed_execution):
    from simple_module_test.tenant_client import create_user, session_client

    user_id = await create_user(app, "no-tenant-resource@test")
    app.state.sm.resource_types.register(
        ResourceType("demo.image", SharedPolicy(), select_by_id(TaskExecution))
    )
    resource = await seed_execution()
    task = await seed_execution(resource_type="demo.image", resource_id=str(resource.id))
    async with session_client(app, {"user_id": user_id}) as client:
        assert (await client.get(URL.format(task.celery_task_id))).status_code == 404


async def test_unexpected_policy_errors_remain_errors(app, tenant_client, seed_execution):
    class BrokenPolicy(SharedPolicy):
        def filter(self, principal, action, stmt):
            raise RuntimeError("policy failed")

    app.state.sm.resource_types.register(
        ResourceType("demo.image", BrokenPolicy(), select_by_id(TaskExecution))
    )
    async with tenant_client(TenantRole.MEMBER) as me:
        resource = await seed_execution(tenant_id=me.tenant_id)
        task = await seed_execution(
            tenant_id=me.tenant_id, resource_type="demo.image", resource_id=str(resource.id)
        )
        with pytest.raises(RuntimeError, match="policy failed"):
            await me.client.get(URL.format(task.celery_task_id))
