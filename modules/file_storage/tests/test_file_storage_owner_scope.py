"""Ordinary users see and change only the files they uploaded (#544).

``file_storage.download``/``upload`` are held by every account, so without an
owner check any member could list, download and publish everyone's files.
Holding ``file_storage.manage`` — platform admins, organisation admins and
owners — widens the scope back to the whole tenant. Someone else's file id
answers 404, exactly like an unknown one, so ids cannot be probed.
"""

from __future__ import annotations

import httpx
import pytest
from file_storage import constants
from simple_module_hosting.settings import Settings
from simple_module_test.tenant_client import create_user, session_client

API = constants.ROUTE_PREFIX_API
VIEW = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


async def _upload(client: httpx.AsyncClient, name: str, body: bytes = b"hi") -> str:
    resp = await client.post(f"{API}/upload", files={"file": (name, body, "text/plain")})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _names(client: httpx.AsyncClient) -> tuple[list[str], int]:
    resp = await client.get(f"{API}/files")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return sorted(f["filename"] for f in body["items"]), body["total"]


class TestMembers:
    async def test_member_lists_only_own_files(self, tenant_client):
        async with (
            tenant_client("member") as a,
            tenant_client("member", tenant_id=a.tenant_id) as b,
        ):
            await _upload(a.client, "a.txt")
            await _upload(b.client, "b.txt")

            assert await _names(a.client) == (["a.txt"], 1)
            assert await _names(b.client) == (["b.txt"], 1)

    async def test_another_members_file_is_not_found(self, tenant_client):
        async with (
            tenant_client("member") as a,
            tenant_client("member", tenant_id=a.tenant_id) as b,
        ):
            file_id = await _upload(a.client, "a.txt")

            assert (await b.client.get(f"{API}/files/{file_id}")).status_code == 404
            assert (await b.client.get(f"{API}/files/{file_id}/download")).status_code == 404
            assert (await b.client.get(f"{API}/files/{file_id}/thumbnail")).status_code == 404
            patch = await b.client.patch(f"{API}/files/{file_id}", json={"public": True})
            assert patch.status_code == 404

            # The owner's file is untouched by the attempts, and still theirs.
            own = await a.client.get(f"{API}/files/{file_id}")
            assert own.status_code == 200
            assert own.json()["public"] is False
            download = await a.client.get(f"{API}/files/{file_id}/download")
            assert download.status_code == 200
            assert download.content == b"hi"

    async def test_member_can_publish_own_file(self, tenant_client):
        async with tenant_client("member") as a:
            file_id = await _upload(a.client, "a.txt")
            resp = await a.client.patch(f"{API}/files/{file_id}", json={"public": True})
            assert resp.status_code == 200, resp.text
            assert resp.json()["public"] is True

    async def test_browse_shows_only_own_files_and_facets(self, tenant_client):
        async with (
            tenant_client("member") as a,
            tenant_client("member", tenant_id=a.tenant_id) as b,
        ):
            await _upload(a.client, "a.txt")
            await b.client.post(f"{API}/upload", files={"file": ("b.csv", b"x,y", "text/csv")})

            # The uploader filter cannot widen the scope to someone else.
            resp = await a.client.get(VIEW, params={"uploaded_by": b.user_id}, headers=INERTIA)
            assert resp.status_code == 200, resp.text
            props = resp.json()["props"]

            assert [f["filename"] for f in props["files"]] == ["a.txt"]
            assert props["pagination"]["total"] == 1
            assert [c["value"] for c in props["content_types"]] == ["text/plain"]
            assert [u["id"] for u in props["uploaders"]] == [a.user_id]


class TestManagers:
    @pytest.mark.parametrize("role", ["admin", "owner"])
    async def test_org_admins_see_and_change_every_members_file(self, tenant_client, role):
        async with (
            tenant_client("member") as a,
            tenant_client(role, tenant_id=a.tenant_id) as boss,
        ):
            file_id = await _upload(a.client, "a.txt")

            assert await _names(boss.client) == (["a.txt"], 1)
            assert (await boss.client.get(f"{API}/files/{file_id}/download")).status_code == 200
            patch = await boss.client.patch(f"{API}/files/{file_id}", json={"public": True})
            assert patch.status_code == 200
            assert (await boss.client.delete(f"{API}/files/{file_id}")).status_code == 204

    async def test_platform_admin_sees_every_file(
        self, authenticated_client, admin_tenant_id, tenant_client
    ):
        async with (
            tenant_client("member", tenant_id=admin_tenant_id) as a,
            tenant_client("member", tenant_id=admin_tenant_id) as b,
        ):
            await _upload(a.client, "a.txt")
            await _upload(b.client, "b.txt")

        assert await _names(authenticated_client) == (["a.txt", "b.txt"], 2)
        props = (await authenticated_client.get(VIEW, headers=INERTIA)).json()["props"]
        assert len(props["uploaders"]) == 2


class TestSingleTenant:
    """With tenancy off every account is in one tenant and holds ``delete``."""

    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"multi_tenant": False, "tenant_header": ""})

    async def test_users_cannot_see_or_delete_each_others_files(self, app):
        alice = await create_user(app, "alice@example.com")
        bob = await create_user(app, "bob@example.com")
        async with (
            session_client(app, {"user_id": alice}) as a,
            session_client(app, {"user_id": bob}) as b,
        ):
            file_id = await _upload(a, "a.txt")

            assert await _names(b) == ([], 0)
            assert (await b.delete(f"{API}/files/{file_id}")).status_code == 404
            bulk = await b.post(f"{API}/files/bulk-delete", json={"ids": [file_id]})
            assert bulk.json() == {"deleted": 0, "ids": []}

            assert await _names(a) == (["a.txt"], 1)
            assert (await a.delete(f"{API}/files/{file_id}")).status_code == 204
