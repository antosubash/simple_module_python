"""Direct tests for the ``tenant`` shared Inertia prop provider."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from starlette.requests import Request
from tenants import resolver
from tenants.constants import TenantStatus
from tenants.contracts.schemas import MyTenantView
from tenants.shared_props import tenant_shared_props

CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _view(tenant_id: str, role: str = "member") -> MyTenantView:
    return MyTenantView(
        id=tenant_id,
        slug=tenant_id,
        name=f"Org {tenant_id}",
        status=TenantStatus.ACTIVE,
        created_at=CREATED,
        role=role,
    )


def _request(**state: Any) -> Request:
    # The provider only reads ``request.state``; a real ASGI scope isn't needed.
    return cast("Request", SimpleNamespace(state=SimpleNamespace(**state)))


@pytest.fixture(autouse=True)
def _clean_cache():
    resolver._MEMBERSHIPS.clear()
    yield
    resolver._MEMBERSHIPS.clear()


def test_anonymous_request_contributes_nothing():
    assert tenant_shared_props(_request()) == {}
    assert tenant_shared_props(_request(user=None)) == {}


def test_user_with_no_cached_memberships_gets_empty_lists():
    request = _request(user=SimpleNamespace(id="u1"), tenant_id=None)
    assert tenant_shared_props(request) == {
        "tenant": {"active": None, "memberships": [], "suspended": False}
    }


def test_active_tenant_is_the_membership_matching_request_tenant_id():
    resolver._MEMBERSHIPS["u1"] = [_view("acme", "owner"), _view("globex")]
    request = _request(user=SimpleNamespace(id="u1"), tenant_id="globex")

    tenant = tenant_shared_props(request)["tenant"]

    assert tenant["active"]["id"] == "globex"
    assert tenant["active"]["role"] == "member"
    assert [m["id"] for m in tenant["memberships"]] == ["acme", "globex"]


def test_active_is_none_when_the_resolved_tenant_is_not_a_membership():
    resolver._MEMBERSHIPS["u1"] = [_view("acme")]
    request = _request(user=SimpleNamespace(id="u1"), tenant_id="elsewhere")

    tenant = tenant_shared_props(request)["tenant"]

    assert tenant["active"] is None
    assert len(tenant["memberships"]) == 1


def test_memberships_are_json_safe():
    resolver._MEMBERSHIPS["u1"] = [_view("acme", "admin")]
    request = _request(user=SimpleNamespace(id="u1"), tenant_id="acme")

    tenant = tenant_shared_props(request)["tenant"]

    # ``mode="json"`` turns the datetime into a string Inertia can serialise.
    assert tenant["active"]["created_at"] == CREATED.isoformat().replace("+00:00", "Z")
    assert isinstance(tenant["memberships"][0]["created_at"], str)


def test_suspended_flag_follows_request_state():
    resolver._MEMBERSHIPS["u1"] = [_view("acme")]
    request = _request(user=SimpleNamespace(id="u1"), tenant_id="acme", tenant_suspended=True)
    assert tenant_shared_props(request)["tenant"]["suspended"] is True


def test_memberships_are_looked_up_by_the_users_own_id_only():
    resolver._MEMBERSHIPS["someone-else"] = [_view("secret-org")]
    request = _request(user=SimpleNamespace(id="u1"), tenant_id="secret-org")

    tenant = tenant_shared_props(request)["tenant"]

    assert tenant["memberships"] == []
    assert tenant["active"] is None


def test_user_id_is_stringified_for_the_cache_lookup():
    import uuid

    uid = uuid.uuid4()
    resolver._MEMBERSHIPS[str(uid)] = [_view("acme")]
    request = _request(user=SimpleNamespace(id=uid), tenant_id="acme")

    assert tenant_shared_props(request)["tenant"]["active"]["id"] == "acme"
