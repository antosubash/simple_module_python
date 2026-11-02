"""Flag changes must survive commit before reaching any worker's registry."""

import pytest
from feature_flags.models import FeatureFlagOverride
from feature_flags.service import FeatureFlagService
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.invalidation import Invalidation
from simple_module_db.transaction import finalize_session, rollback_session


@pytest.mark.parametrize("commit", [False, True])
@pytest.mark.parametrize("scope,scope_id", [("system", ""), ("tenant", "acme")])
@pytest.mark.parametrize("clear", [False, True])
async def test_flag_mutation_waits_for_commit(db_session, commit, scope, scope_id, clear):
    registry = FeatureFlagRegistry()
    registry.add(FeatureFlagDefinition("switch"))
    tenant_id = scope_id or None
    if clear:
        db_session.add(
            FeatureFlagOverride(scope=scope, scope_id=scope_id, name="switch", enabled=True)
        )
        await db_session.commit()
        registry.set_override("switch", True, tenant_id=tenant_id)
    service = FeatureFlagService(db_session)
    if clear:
        await service.clear_override("switch", registry, scope, scope_id)
    else:
        await service.set_override("switch", True, registry, scope, scope_id)
    assert registry.is_enabled("switch", tenant_id) is clear
    if commit:
        await finalize_session(db_session)
    else:
        await rollback_session(db_session)
    assert registry.is_enabled("switch", tenant_id) is (clear != commit)


@pytest.mark.parametrize("scope,scope_id", [("system", ""), ("tenant", "acme")])
async def test_remote_flag_changes_and_deletions_reload(app, scope, scope_id):
    registry = app.state.sm.feature_flags
    registry.add(FeatureFlagDefinition("switch"))
    factory = app.state.sm.db.session_factory
    async with factory() as db:
        row = FeatureFlagOverride(scope=scope, scope_id=scope_id, name="switch", enabled=True)
        db.add(row)
        await db.commit()
        row_id = row.id
    bus = app.state.sm.invalidation
    message = Invalidation(channel="feature_flags.overrides", origin="other")
    await bus.deliver(message.to_wire())
    assert registry.is_enabled("switch", scope_id or None) is True
    async with factory() as db:
        await db.delete(await db.get(FeatureFlagOverride, row_id))
        await db.commit()
    await bus.deliver(message.to_wire())
    assert registry.is_enabled("switch", scope_id or None) is False


@pytest.mark.parametrize("commit", [False, True])
@pytest.mark.parametrize("scope,scope_id", [("system", ""), ("tenant", "acme")])
async def test_flag_request_publishes_only_after_commit(app, commit, scope, scope_id):
    from feature_flags.deps import get_feature_flag_service
    from starlette.requests import Request

    registry = app.state.sm.feature_flags
    registry.add(FeatureFlagDefinition("switch"))
    messages = []
    app.state.sm.invalidation.subscribe("feature_flags.overrides", messages.append)
    async with app.state.sm.db.session_factory() as db:
        service = await get_feature_flag_service(Request({"type": "http", "app": app}), db)
        await service.set_override("switch", True, registry, scope, scope_id)
        assert registry.is_enabled("switch", scope_id or None) is False
        assert messages == []
        if commit:
            await finalize_session(db)
        else:
            await rollback_session(db)
    assert registry.is_enabled("switch", scope_id or None) is commit
    assert len(messages) == int(commit)
