"""REST API tests for scoped settings endpoints."""

from __future__ import annotations

import httpx
from settings.constants import (
    API_PREFIX,
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_NOT_FOUND,
)


def _url(path: str = "") -> str:
    return f"{API_PREFIX}/{path.lstrip('/')}" if path else f"{API_PREFIX}/"


class TestScopedAPI:
    async def test_list_empty(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url())
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_upsert_and_get_system(self, authenticated_client: httpx.AsyncClient):
        put = await authenticated_client.put(_url("system/feature.x"), json={"value": "on"})
        assert put.status_code == 200
        got = await authenticated_client.get(_url("system/feature.x"))
        assert got.status_code == 200
        assert got.json()["value"] == "on"
        assert got.json()["scope"] == "system"

    async def test_upsert_tenant_setting(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(_url("tenant/acme/feature.x"), json={"value": "ten"})
        assert resp.status_code == 200
        assert resp.json()["scope"] == "tenant"
        assert resp.json()["scope_id"] == "acme"

    async def test_upsert_user_setting(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(_url("user/u-123/feature.x"), json={"value": "usr"})
        assert resp.status_code == 200
        assert resp.json()["scope"] == "user"

    async def test_resolve_user_beats_tenant(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(_url("system/feature.x"), json={"value": "sys"})
        await authenticated_client.put(_url("tenant/acme/feature.x"), json={"value": "ten"})
        await authenticated_client.put(_url("user/u-1/feature.x"), json={"value": "usr"})
        resp = await authenticated_client.get(
            _url("resolve/feature.x"),
            params={"user_id": "u-1", "tenant_id": "acme"},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "usr"

    async def test_resolve_tenant_beats_system(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(_url("system/feature.x"), json={"value": "sys"})
        await authenticated_client.put(_url("tenant/acme/feature.x"), json={"value": "ten"})
        resp = await authenticated_client.get(
            _url("resolve/feature.x"), params={"tenant_id": "acme"}
        )
        assert resp.json()["value"] == "ten"

    async def test_resolve_falls_through_to_system(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(_url("system/feature.x"), json={"value": "sys"})
        resp = await authenticated_client.get(
            _url("resolve/feature.x"),
            params={"user_id": "u-1", "tenant_id": "acme"},
        )
        assert resp.json()["value"] == "sys"

    async def test_resolve_missing_returns_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url("resolve/missing"))
        assert resp.status_code == STATUS_NOT_FOUND

    async def test_filter_list_by_scope(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(_url("system/a"), json={"value": "1"})
        await authenticated_client.put(_url("tenant/t1/a"), json={"value": "2"})
        await authenticated_client.put(_url("tenant/t2/a"), json={"value": "3"})
        resp = await authenticated_client.get(_url(), params={"scope": "tenant", "scope_id": "t1"})
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["scope_id"] == "t1"

    async def test_delete_tenant_setting(self, authenticated_client: httpx.AsyncClient):
        await authenticated_client.put(_url("tenant/acme/x"), json={"value": "v"})
        resp = await authenticated_client.delete(_url("tenant/acme/x"))
        assert resp.status_code == STATUS_NO_CONTENT
        assert (
            await authenticated_client.get(_url("tenant/acme/x"))
        ).status_code == STATUS_NOT_FOUND

    async def test_create_via_post(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            _url(),
            json={"scope": "tenant", "scope_id": "acme", "key": "k", "value": "v"},
        )
        assert resp.status_code == STATUS_CREATED
        assert resp.json()["scope"] == "tenant"

    async def test_create_invalid_scope_mismatch(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.post(
            _url(),
            json={"scope": "system", "scope_id": "acme", "key": "k", "value": "v"},
        )
        assert resp.status_code == 422

    async def test_update_by_id(self, authenticated_client: httpx.AsyncClient):
        post = await authenticated_client.post(_url(), json={"key": "k", "value": "old"})
        item_id = post.json()["id"]
        put = await authenticated_client.put(_url(str(item_id)), json={"value": "new"})
        assert put.status_code == 200
        assert put.json()["value"] == "new"

    async def test_get_id_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(_url("99999"))
        assert resp.status_code == STATUS_NOT_FOUND

    async def test_upsert_with_value_type(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            _url("system/rate.limit"),
            json={"value": "42", "value_type": "int"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["value_type"] == "int"
        assert body["value"] == "42"

    async def test_upsert_rejects_value_type_mismatch(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.put(
            _url("system/rate.limit"),
            json={"value": "nope", "value_type": "int"},
        )
        assert resp.status_code == 422

    async def test_default_value_type_is_string(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(_url("system/label"), json={"value": "hi"})
        assert resp.status_code == 200
        assert resp.json()["value_type"] == "string"
