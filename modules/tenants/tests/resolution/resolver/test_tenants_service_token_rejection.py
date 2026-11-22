"""Service tokens lose their principal when their tenant is unavailable (#1070)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from simple_module_db.models.listeners import current_user_id
from starlette.requests import Request
from tenants.core.constants import TenantStatus
from tenants.resolution.token_tenant import _service_tenant


@pytest.mark.parametrize("tenant", [None, SimpleNamespace(status=TenantStatus.SUSPENDED)])
async def test_unavailable_service_tenant_forgets_principal(tenant):
    db = AsyncMock()
    db.get.return_value = tenant
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    app = SimpleNamespace(
        state=SimpleNamespace(sm=SimpleNamespace(db=SimpleNamespace(session_factory=factory)))
    )
    request = Request(
        {"type": "http", "app": app, "state": {"user": object(), "resolved_permissions": {"write"}}}
    )
    token = current_user_id.set("service-key")
    try:
        assert await _service_tenant(request, "a" * 32) is None
        assert request.state.user is None
        assert request.state.resolved_permissions == set()
        assert current_user_id.get() is None
    finally:
        current_user_id.reset(token)
