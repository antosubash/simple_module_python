"""The admin Edit page lists an account's linked sign-ins (#877)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from users.models import OAuthAccount

_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


@pytest.mark.anyio
async def test_edit_page_lists_linked_sign_ins(admin_client, users_db):
    from _users_admin_support import _make_user

    user = await _make_user(users_db, email="linked@example.com")
    signed_in = datetime(2026, 11, 1, 9, 30, tzinfo=UTC)
    link = OAuthAccount(
        user_id=user.id,
        oauth_name="microsoft",
        access_token="at",
        account_id="oid-1",
        account_email="linked@example.com",
        subject="pairwise-sub",
        username="linked@example.com",
        last_sign_in_at=signed_in,
    )
    users_db.add(link)
    await users_db.commit()

    resp = await admin_client.get(f"/admin/users/{user.id}", headers=_INERTIA)

    assert resp.status_code == 200
    assert resp.json()["props"]["linked_sign_ins"] == [
        {
            "id": str(link.id),
            "provider": "microsoft",
            "username": "linked@example.com",
            "subject": "pairwise-sub",
            "last_sign_in_at": signed_in.isoformat(),
        }
    ]


@pytest.mark.anyio
async def test_a_local_account_has_none(admin_client, users_db):
    from _users_admin_support import _make_user

    user = await _make_user(users_db, email="local@example.com")
    resp = await admin_client.get(f"/admin/users/{user.id}", headers=_INERTIA)
    assert resp.json()["props"]["linked_sign_ins"] == []
    assert resp.json()["props"]["has_duplicate_linked_sign_ins"] is False


@pytest.mark.anyio
async def test_duplicate_warning_uses_provider_key(admin_client, users_app, users_db):
    from _users_admin_support import _make_user
    from _users_oauth_support import install_fake_provider

    user = await _make_user(users_db, email="duplicates@example.com")
    for provider in ("oidc", "github"):
        install_fake_provider(users_app, "id", user.email, provider=provider)
        users_app.state.users.oauth_clients[provider] = users_app.state.users.oauth_clients[
            provider
        ]._replace(display_name="Same")
    users_db.add_all(
        [
            OAuthAccount(
                user_id=user.id,
                oauth_name=provider,
                account_id=str(i),
                account_email=user.email,
                access_token="at",
            )
            for i, provider in enumerate(("oidc", "github"))
        ]
    )
    await users_db.commit()
    page = await admin_client.get(f"/admin/users/{user.id}", headers={"X-Inertia": "true"})
    assert page.json()["props"]["has_duplicate_linked_sign_ins"] is False

    users_db.add(
        OAuthAccount(
            user_id=user.id,
            oauth_name="oidc",
            account_id="second",
            account_email=user.email,
            access_token="at",
        )
    )
    await users_db.commit()
    page = await admin_client.get(f"/admin/users/{user.id}", headers={"X-Inertia": "true"})
    assert page.json()["props"]["has_duplicate_linked_sign_ins"] is True
