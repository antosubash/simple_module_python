"""Admin detail API mirrors the Edit page props exactly; unlink needs CSRF for cookies."""

from __future__ import annotations

import pytest
from _users_admin_support import _make_user
from users.models import OAuthAccount

_BASE = "/api/users/admin"


@pytest.fixture
async def linked(users_db):
    user = await _make_user(users_db, "shape@example.com", role_names=["user"])
    links = [
        OAuthAccount(
            user_id=user.id,
            oauth_name="github",
            account_id=f"sid-{i}",
            account_email=user.email,
            access_token="secret-access",
            refresh_token="secret-refresh",
        )
        for i in range(2)
    ]
    users_db.add_all(links)
    await users_db.commit()
    return user, links


async def _props(client, user_id) -> dict:
    page = await client.get(f"/admin/users/{user_id}", headers={"X-Inertia": "true"})
    assert page.status_code == 200
    return page.json()["props"]


@pytest.mark.anyio
async def test_responses_equal_view_props_exactly(admin_client, linked):
    user, _ = linked
    props = await _props(admin_client, user.id)

    got_user = (await admin_client.get(f"{_BASE}/{user.id}")).json()
    assert set(got_user) == set(props["user"])
    assert got_user == props["user"]

    roles = (await admin_client.get(f"{_BASE}/roles")).json()
    assert roles == props["roles"]
    assert all(set(r) == {"id", "name"} for r in roles)

    body = (await admin_client.get(f"{_BASE}/{user.id}/linked-sign-ins")).json()
    assert set(body) == {"linked_sign_ins", "has_duplicate_linked_sign_ins"}
    assert body["linked_sign_ins"] == props["linked_sign_ins"]
    assert body["has_duplicate_linked_sign_ins"] == props["has_duplicate_linked_sign_ins"]
    for item in body["linked_sign_ins"]:
        assert set(item) == {"id", "provider", "username", "subject", "last_sign_in_at"}


@pytest.mark.anyio
async def test_cookie_unlink_requires_csrf(admin_client, linked):
    user, links = linked
    url = f"{_BASE}/{user.id}/linked-sign-ins/{links[0].id}"
    assert (await admin_client.delete(url)).status_code == 403
    token = (await _props(admin_client, user.id))["csrfToken"]
    resp = await admin_client.delete(url, headers={"X-CSRF-Token": token})
    assert resp.status_code == 204, resp.text
