"""Optional modules purge tenant data in the request without background tasks."""

from datetime import UTC, datetime, timedelta

import pytest
from api_tokens.models import ApiToken
from api_tokens.module import ApiTokensModule
from feature_flags.models import FeatureFlagOverride
from feature_flags.module import FeatureFlagsModule
from sharing.models import ResourceShare
from sharing.module import SharingModule
from simple_module_core.events import EventBus
from simple_module_db import all_tenants, tenant_context
from simple_module_db.stored_settings import SCOPE_TENANT, Setting
from simple_module_db.tenant_cleanup import register_tenant_cleanup
from simple_module_db.transaction import finalize_session, rollback_session
from sqlmodel import select
from tenants.models import Tenant
from tenants.service import TenantService


@pytest.mark.parametrize("rollback", [False, True])
async def test_inline_deletion_purges_rows_atomically(db_session, rollback):
    bus = EventBus()
    for module in (ApiTokensModule(), SharingModule(), FeatureFlagsModule()):
        module.register_event_handlers(bus)
    register_tenant_cleanup(bus)
    for tenant_id in ("deleted", "retained"):
        db_session.add(Tenant(id=tenant_id, slug=tenant_id, name=tenant_id))
        with tenant_context(tenant_id):
            db_session.add(
                ApiToken(
                    name="token",
                    prefix="test",
                    token_hash=tenant_id,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            db_session.add(
                ResourceShare(
                    resource_type="test.note",
                    resource_id="note",
                    subject_id="user",
                    role="view",
                    granted_by="owner",
                )
            )
            await db_session.flush()
        db_session.add(FeatureFlagOverride(scope=SCOPE_TENANT, scope_id=tenant_id, name="flag"))
        db_session.add(Setting(scope=SCOPE_TENANT, scope_id=tenant_id, key="key", value="value"))
    await finalize_session(db_session)
    await TenantService(db_session, bus=bus).delete_tenant("deleted")
    with all_tenants():
        for model in (ApiToken, ResourceShare, FeatureFlagOverride, Setting):
            assert len((await db_session.execute(select(model))).scalars().all()) == 1
    if rollback:
        await rollback_session(db_session)
    else:
        await finalize_session(db_session)
    with all_tenants():
        for model in (Tenant, ApiToken, ResourceShare, FeatureFlagOverride, Setting):
            assert len((await db_session.execute(select(model))).scalars().all()) == (
                2 if rollback else 1
            )
