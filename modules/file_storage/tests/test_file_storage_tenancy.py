"""``StoredFile`` is tenant-scoped (#383): one organisation never sees another's files.

Every route answers for the active tenant only — another tenant's file id is
indistinguishable from an unknown one (404, never 403, so ids cannot be probed),
listings and bucket totals count only the tenant's own rows, and the backend
namespaces are disjoint because new keys start with ``{tenant_id}/``.
"""

from __future__ import annotations

import httpx
import pytest
from file_storage import constants
from file_storage.models import StoredFile
from simple_module_db import tenant_context
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

API = constants.ROUTE_PREFIX_API
VIEW = f"{constants.ROUTE_PREFIX_VIEW}/"
INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


async def _upload(client: httpx.AsyncClient, name: str = "a.txt", body: bytes = b"hi") -> dict:
    resp = await client.post(f"{API}/upload", files={"file": (name, body, "text/plain")})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _browse(client: httpx.AsyncClient) -> dict:
    resp = await client.get(VIEW, headers=INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


class TestCrossTenantAccess:
    async def test_another_tenants_file_is_not_found(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            file_id = (await _upload(a.client))["id"]

            assert (await b.client.get(f"{API}/files/{file_id}")).status_code == 404
            assert (await b.client.get(f"{API}/files/{file_id}/download")).status_code == 404
            assert (await b.client.delete(f"{API}/files/{file_id}")).status_code == 404

            # ...and the owner still has it, untouched by the attempts.
            assert (await a.client.get(f"{API}/files/{file_id}")).status_code == 200
            download = await a.client.get(f"{API}/files/{file_id}/download")
            assert download.status_code == 200
            assert download.content == b"hi"

    async def test_bulk_delete_skips_another_tenants_ids(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            file_id = (await _upload(a.client))["id"]

            resp = await b.client.post(f"{API}/files/bulk-delete", json={"ids": [file_id]})

            assert resp.status_code == 200, resp.text
            assert resp.json() == {"deleted": 0, "ids": []}
            assert (await a.client.get(f"{API}/files/{file_id}")).status_code == 200

    async def test_listing_shows_only_the_tenants_own_files(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            await _upload(a.client, "a.txt")
            await _upload(b.client, "b.txt")

            a_list = (await a.client.get(f"{API}/files")).json()
            b_list = (await b.client.get(f"{API}/files")).json()

            assert [f["filename"] for f in a_list["items"]] == ["a.txt"]
            assert [f["filename"] for f in b_list["items"]] == ["b.txt"]
            assert a_list["total"] == b_list["total"] == 1


class TestKeys:
    async def test_new_keys_are_prefixed_with_the_tenant(self, app, tenant_client):
        async with tenant_client() as a:
            out = await _upload(a.client)

        assert out["key"].startswith(f"{a.tenant_id}/")
        # The bytes live under that prefix on the backend, not just in the row.
        assert await app.state.file_storage.backend.exists(out["key"])

    async def test_the_same_key_can_exist_in_two_tenants(self, app):
        def row(tenant_id: str) -> StoredFile:
            return StoredFile(
                tenant_id=tenant_id,
                key="shared/key.txt",
                filename="key.txt",
                content_type="text/plain",
                size_bytes=1,
                backend=constants.BackendId.FILESYSTEM,
                checksum_sha256="0" * 64,
            )

        for tenant_id in ("t-one", "t-two"):
            with tenant_context(tenant_id):
                async with app.state.sm.db.session_factory() as session:
                    session.add(row(tenant_id))
                    await session.commit()

        # Still unique *within* a tenant.
        with tenant_context("t-one"), pytest.raises(IntegrityError):
            async with app.state.sm.db.session_factory() as session:
                session.add(row("t-one"))
                await session.commit()

        with tenant_context("t-two"):
            async with app.state.sm.db.session_factory() as session:
                rows = (await session.execute(select(StoredFile))).scalars().all()
        assert [(r.tenant_id, r.key) for r in rows] == [("t-two", "shared/key.txt")]


class TestAggregates:
    async def test_totals_and_facets_are_per_tenant(self, tenant_client):
        async with tenant_client() as a, tenant_client() as b:
            await _upload(a.client, "a.txt", b"12345")

            a_props = await _browse(a.client)
            b_props = await _browse(b.client)

            assert a_props["used_bytes"] == 5
            assert [f["value"] for f in a_props["content_types"]] == ["text/plain"]
            assert [u["id"] for u in a_props["uploaders"]] == [a.user_id]
            assert b_props["used_bytes"] == 0
            assert b_props["content_types"] == []
            assert b_props["uploaders"] == []

    async def test_a_cached_tenant_total_never_answers_another_tenant(self, tenant_client):
        """The cache is warm for A before B renders — B must still get its own."""
        async with tenant_client() as a, tenant_client() as b:
            await _upload(a.client, "a.txt", b"123")
            await _upload(b.client, "b.txt", b"1234567")

            assert (await _browse(a.client))["used_bytes"] == 3
            assert (await _browse(b.client))["used_bytes"] == 7
            assert (await _browse(a.client))["used_bytes"] == 3

            # B's write drops B's slot; A's next render is still A's number.
            await _upload(b.client, "c.txt", b"1")
            assert (await _browse(b.client))["used_bytes"] == 8
            assert (await _browse(a.client))["used_bytes"] == 3


class TestTenantRoles:
    async def test_a_member_can_upload_and_download_but_not_delete(self, tenant_client):
        async with tenant_client("member") as member:
            file_id = (await _upload(member.client))["id"]

            assert (await member.client.get(f"{API}/files/{file_id}/download")).status_code == 200
            assert (await member.client.delete(f"{API}/files/{file_id}")).status_code == 403

    @pytest.mark.parametrize("role", ["admin", "owner"])
    async def test_admins_and_owners_can_delete(self, tenant_client, role):
        async with tenant_client(role) as boss:
            file_id = (await _upload(boss.client))["id"]

            assert (await boss.client.delete(f"{API}/files/{file_id}")).status_code == 204
            assert (await boss.client.get(f"{API}/files/{file_id}")).status_code == 404

    async def test_members_see_the_files_menu_entry(self, tenant_client):
        async with tenant_client("member") as member:
            props = await _browse(member.client)

        urls = [item["url"] for item in props["menus"]["sidebar"]]
        assert f"{constants.ROUTE_PREFIX_VIEW}/" in urls


class TestCacheSlots:
    async def test_a_write_drops_only_its_own_tenants_slot(self, db_session, db_state):
        from file_storage.aggregates import AggregateCache, register_invalidation

        cache = AggregateCache()
        register_invalidation(db_state, cache)
        for tenant_id in ("t-one", "t-two"):
            with tenant_context(tenant_id):
                await cache.get(db_session)

        with tenant_context("t-one"):
            async with db_state.session_factory() as other:
                other.add(
                    StoredFile(
                        key="k",
                        filename="k.txt",
                        content_type="text/plain",
                        size_bytes=4,
                        backend=constants.BackendId.FILESYSTEM,
                        checksum_sha256="0" * 64,
                    )
                )
                await other.commit()
            assert cache.peek() is None
        with tenant_context("t-two"):
            assert cache.peek() is not None


class TestAuditLabels:
    async def test_the_platform_audit_log_names_every_tenants_files(self, app, tenant_client):
        """The audit log lists every tenant's entries (and already records the
        filename in each), so its resolver names files across tenants — and
        works for a platform admin with no tenant bound."""
        from file_storage.module import _resolve_file_labels

        async with tenant_client() as a, tenant_client() as b:
            a_id = (await _upload(a.client, "a.txt"))["id"]
            b_id = (await _upload(b.client, "b.txt"))["id"]

        async with app.state.sm.db.session_factory() as session:
            labels = await _resolve_file_labels(session, [a_id, b_id])

        assert labels == {a_id: "a.txt", b_id: "b.txt"}
