"""A real tenant deletion delivers every installed owner's durable teardown."""

from datetime import UTC, datetime, timedelta

from api_tokens.models import ApiToken
from audit_log.models import AuditEntry
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from feature_flags.models import FeatureFlagOverride
from file_storage.backends.filesystem import FilesystemBackend
from file_storage.models import StoredFile
from simple_module_db import all_tenants, tenant_context
from simple_module_db.stored_settings import SCOPE_TENANT, Setting
from sqlmodel import select
from tenants.service import TenantService


async def test_tenants_delete_removes_owned_data_but_retains_audit(
    app, tenant_client, client, tmp_path, monkeypatch
):
    app.state.background_tasks.settings.task_always_eager = True
    backend = FilesystemBackend(tmp_path)
    app.state.file_storage.backend = backend
    monkeypatch.setattr("file_storage.tenant_deletion.build_backend", lambda settings: backend)
    async with tenant_client() as owner:
        response = await owner.client.post(
            "/api/file-storage/upload",
            files={"file": ("public.txt", b"tenant bytes", "text/plain")},
            data={"public": "true"},
        )
        assert response.status_code == 201, response.text
        public_url = response.json()["public_url"]
        assert (await client.get(public_url)).status_code == 200
        factory = app.state.sm.db.session_factory
        with tenant_context(owner.tenant_id):
            async with factory() as db:
                db.add(
                    ApiToken(
                        name="tenant credential",
                        prefix="test",
                        token_hash="a" * 64,
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                    )
                )
                db.add(
                    Setting(
                        scope=SCOPE_TENANT,
                        scope_id=owner.tenant_id,
                        key="branding.logo_file_id",
                        value="old-file",
                    )
                )
                db.add(
                    FeatureFlagOverride(
                        scope=SCOPE_TENANT,
                        scope_id=owner.tenant_id,
                        name="test.tenant-feature",
                        enabled=True,
                    )
                )
                audit = AuditEntry(
                    entity_type="Tenant",
                    entity_id=owner.tenant_id,
                    action="created",
                    tenant_id=owner.tenant_id,
                )
                db.add(audit)
                await db.commit()
                audit_id = audit.id
        async with factory() as db:
            await TenantService(db, bus=app.state.sm.event_bus).delete_tenant(owner.tenant_id)
            await db.commit()
        transport = app.state.sm.event_bus.durable_transport
        await transport.drain()
        await dispatch(
            factory, app.state.sm.event_bus, OutboxPolicy(max_attempts=8, lease_seconds=300)
        )
        assert (await client.get(public_url)).status_code == 404
        with all_tenants():
            async with factory() as db:
                for model in (StoredFile, ApiToken):
                    assert (
                        not (
                            await db.execute(
                                select(model)
                                .where(model.tenant_id == owner.tenant_id)
                                .execution_options(include_deleted=True)
                            )
                        )
                        .scalars()
                        .all()
                    )
                assert (
                    not (
                        await db.execute(
                            select(Setting).where(
                                Setting.scope == SCOPE_TENANT, Setting.scope_id == owner.tenant_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert (
                    not (
                        await db.execute(
                            select(FeatureFlagOverride).where(
                                FeatureFlagOverride.scope == SCOPE_TENANT,
                                FeatureFlagOverride.scope_id == owner.tenant_id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                retained = await db.get(AuditEntry, audit_id)
                assert retained is not None and retained.tenant_id == owner.tenant_id
        assert not any(path.is_file() for path in tmp_path.rglob("*"))
