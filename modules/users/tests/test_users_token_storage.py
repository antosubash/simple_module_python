"""Bearer secrets stay out of storage and spent credentials are pruned (#626)."""

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from users.models import RefreshToken, UserAccessToken


async def _login(client):
    response = await client.post(
        "/api/users/auth/token",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
async def test_users_pair_stores_digests_and_accepts_only_presented_secrets(anon_client, users_db):
    pair = await _login(anon_client)
    for model, key in ((UserAccessToken, "access_token"), (RefreshToken, "refresh_token")):
        row = (await users_db.execute(select(model))).scalar_one()
        assert row.token == hashlib.sha256(pair[key].encode()).hexdigest()
    assert (
        await anon_client.get(
            "/admin/users/", headers={"Authorization": f"Bearer {pair['access_token']}"}
        )
    ).status_code == 200
    digest = hashlib.sha256(pair["access_token"].encode()).hexdigest()
    assert (
        await anon_client.get("/admin/users/", headers={"Authorization": f"Bearer {digest}"})
    ).status_code in (302, 401)
    rotated = await anon_client.post(
        "/api/users/auth/token/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert rotated.status_code == 200


@pytest.mark.anyio
async def test_users_cookie_token_is_hashed_and_logout_deletes_it(anon_client, users_db):
    response = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1!"},
    )
    assert response.status_code == 204
    secret = anon_client.cookies.get("sm_auth")
    row = (await users_db.execute(select(UserAccessToken))).scalar_one()
    assert row.token == hashlib.sha256(secret.encode()).hexdigest()
    assert (await anon_client.get("/api/users/me")).status_code == 200
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await users_db.commit()
    assert (
        await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!"},
        )
    ).status_code == 204
    assert await users_db.get(UserAccessToken, row.token, populate_existing=True) is None
    assert (await anon_client.post("/api/users/auth/logout")).status_code == 204
    assert (await users_db.execute(select(UserAccessToken))).scalars().all() == []


@pytest.mark.anyio
async def test_users_login_prunes_expired_and_revoked_inactive_families(anon_client, users_db):
    await _login(anon_client)
    refresh = (await users_db.execute(select(RefreshToken))).scalar_one()
    access = (await users_db.execute(select(UserAccessToken))).scalar_one()
    refresh.revoked_at = datetime.now(UTC)
    access.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    old_refresh, old_access = refresh.token, access.token
    await users_db.commit()
    await _login(anon_client)
    assert await users_db.get(RefreshToken, old_refresh, populate_existing=True) is None
    assert await users_db.get(UserAccessToken, old_access, populate_existing=True) is None


@pytest.mark.anyio
async def test_users_pruning_keeps_reuse_evidence_even_for_expired_ancestors(
    anon_client,
    users_db,
):
    pair = await _login(anon_client)
    child = await anon_client.post(
        "/api/users/auth/token/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert child.status_code == 200
    ancestor = await users_db.get(
        RefreshToken, hashlib.sha256(pair["refresh_token"].encode()).hexdigest()
    )
    assert ancestor is not None
    ancestor.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await users_db.commit()
    await _login(anon_client)  # cleanup must preserve this family's reuse evidence
    replay = await anon_client.post(
        "/api/users/auth/token/refresh", json={"refresh_token": pair["refresh_token"]}
    )
    assert replay.status_code == 401
    assert (
        await anon_client.post(
            "/api/users/auth/token/refresh", json={"refresh_token": child.json()["refresh_token"]}
        )
    ).status_code == 401
