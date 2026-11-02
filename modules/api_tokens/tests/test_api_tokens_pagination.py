"""Bound token lists without truncating revoke-all (#640)."""

import uuid

import pytest
from _api_tokens_support import INERTIA_HEADERS, PAT_URL, create_pat
from api_tokens.constants import TokenKind
from api_tokens.service import ApiTokenService
from simple_module_db.tenancy import tenant_context


async def test_service_pages_and_revoke_all(db_session):
    service = ApiTokenService(db_session)
    owner = uuid.uuid4()
    with tenant_context("pagination"):
        made = []
        for i in range(105):
            token, _ = await service.create(
                kind=TokenKind.PERSONAL,
                name=str(i),
                scopes=["api_tokens.use"],
                expires_in_days=1,
                max_lifetime_days=1,
                owner_user_id=owner,
            )
            made.append(token)
        assert len(await service.list_tenant()) == 100
        assert len(await service.list_for_owner(owner)) == 100
        for listing in (service.list_tenant, lambda **kw: service.list_for_owner(owner, **kw)):
            first = await listing(limit=3)
            second = await listing(limit=3, offset=3)
            assert len(first) == len(second) == 3
            assert not {t.id for t in first} & {t.id for t in second}
        assert await service.revoke_all_for_owner(owner) == 105
        assert all(t.revoked_at is not None for t in made)
        assert await service.revoke_all_for_owner(owner) == 0


@pytest.mark.parametrize("url", [PAT_URL, "/api/api_tokens/admin/tokens"])
async def test_http_pages_and_bounds(actor, url):
    async with actor(admin=True) as a:
        for _ in range(3):
            await create_pat(a.client, ["api_tokens.use"])
        first = await a.client.get(url, params={"limit": 1})
        second = await a.client.get(url, params={"limit": 1, "offset": 1})
        assert first.status_code == second.status_code == 200
        assert len(first.json()) == len(second.json()) == 1
        assert first.json()[0]["id"] != second.json()[0]["id"]
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            assert (await a.client.get(url, params=params)).status_code == 422


@pytest.mark.parametrize("url", ["/api-tokens/", "/admin/api-tokens/"])
async def test_pages_expose_navigation_without_extra_row(actor, url):
    async with actor(admin=True) as a:
        for _ in range(3):
            await create_pat(a.client, ["api_tokens.use"])
        first = await a.client.get(url, params={"limit": 2}, headers=INERTIA_HEADERS)
        assert first.status_code == 200
        props = first.json()["props"]
        assert len(props["tokens"]) == 2
        assert props["pagination"] == {"limit": 2, "offset": 0, "has_more": True}
        last = await a.client.get(url, params={"limit": 2, "offset": 2}, headers=INERTIA_HEADERS)
        props = last.json()["props"]
        assert len(props["tokens"]) == 1
        assert props["pagination"] == {"limit": 2, "offset": 2, "has_more": False}
