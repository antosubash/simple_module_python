"""A tenant switch changes the effective principal's tenant role context."""

from simple_module_hosting.csrf import get_csrf_token
from starlette.requests import Request
from tenants.constants import SESSION_ACTIVE_TENANT
from tenants.resolver import switch_active


def test_switch_discards_previous_tenants_token():
    request = Request({"type": "http", "session": {"user_id": "same-user"}})
    old = get_csrf_token(request)
    switch_active(request, "another-tenant")
    assert request.session[SESSION_ACTIVE_TENANT] == "another-tenant"
    assert request.session["user_id"] == "same-user"
    assert get_csrf_token(request) != old
