"""Tenants, switching and membership management through the HTTP API."""

from __future__ import annotations


async def _create(client, name: str) -> dict:
    resp = await client.post("/api/tenants/", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_creator_becomes_owner_and_active(user_client):
    async with user_client("owner@acme.io") as (client, user_id):
        tenant = await _create(client, "Acme Inc")
        assert tenant["role"] == "owner"
        assert tenant["slug"] == "acme-inc"

        members = (await client.get("/api/tenants/current/members")).json()
        assert [(m["user_id"], m["role"], m["email"]) for m in members] == [
            (user_id, "owner", "owner@acme.io")
        ]


async def test_slug_collision_gets_suffix(user_client):
    async with user_client("a@x.io") as (a, _), user_client("b@x.io") as (b, _):
        first = await _create(a, "Same Name")
        second = await _create(b, "Same Name")
        assert first["slug"] == "same-name"
        assert second["slug"].startswith("same-name-")


async def test_user_sees_only_their_tenants(user_client):
    async with user_client("a@x.io") as (a, _), user_client("b@x.io") as (b, _):
        await _create(a, "Alpha")
        await _create(b, "Beta")
        names = [t["name"] for t in (await a.get("/api/tenants/")).json()]
        assert names == ["Alpha"]


async def test_cannot_switch_into_foreign_tenant(user_client):
    async with user_client("a@x.io") as (a, _), user_client("b@x.io") as (b, _):
        foreign = await _create(b, "Beta")
        resp = await a.post(f"/api/tenants/{foreign['id']}/switch")
        assert resp.status_code == 404


async def test_switch_between_own_tenants(user_client):
    async with user_client("a@x.io") as (a, _):
        one = await _create(a, "One")
        two = await _create(a, "Two")
        assert (await a.post(f"/api/tenants/{one['id']}/switch")).status_code == 204
        page = await a.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["active_id"] == one["id"]
        assert (await a.post(f"/api/tenants/{two['id']}/switch")).status_code == 204
        page = await a.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["active_id"] == two["id"]


async def test_member_without_tenant_gets_403_on_tenant_api(user_client):
    async with user_client("lonely@x.io") as (client, _):
        resp = await client.get("/api/tenants/current/members")
        assert resp.status_code == 403


async def test_last_owner_cannot_leave_or_be_demoted(tenant_client):
    async with tenant_client("owner") as (client, _, user_id):
        assert (await client.delete("/api/tenants/current/membership")).status_code == 409
        resp = await client.patch(f"/api/tenants/current/members/{user_id}", json={"role": "admin"})
        assert resp.status_code == 409


async def test_tenant_admin_is_not_platform_admin(tenant_client):
    async with tenant_client("owner") as (client, _, _):
        assert (await client.get("/api/tenants/admin/")).status_code == 403
        assert (await client.get("/admin/tenants/")).status_code in (302, 303, 403)


async def test_self_service_can_be_disabled(app, user_client):
    app.state.tenants.settings.allow_self_service = False
    try:
        async with user_client("a@x.io") as (client, _):
            resp = await client.post("/api/tenants/", json={"name": "Nope"})
            assert resp.status_code == 403
    finally:
        app.state.tenants.settings.allow_self_service = True


async def test_header_selects_a_tenant_the_user_belongs_to(user_client):
    # The test settings configure tenant_header="X-Tenant-ID".
    async with user_client("a@x.io") as (a, _), user_client("b@x.io") as (b, _):
        one = await _create(a, "One")
        two = await _create(a, "Two")  # active in the session now
        foreign = await _create(b, "Foreign")

        page = await a.get("/tenants/", headers={"X-Inertia": "true", "X-Tenant-ID": one["id"]})
        assert page.json()["props"]["active_id"] == one["id"]
        # The header is per request: the session choice is untouched.
        page = await a.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["active_id"] == two["id"]

        # A tenant the user is not in resolves to nothing — no silent fallback.
        resp = await a.get("/api/tenants/current/members", headers={"X-Tenant-ID": foreign["id"]})
        assert resp.status_code == 403


async def test_malformed_header_resolves_to_nothing(user_client):
    async with user_client("a@x.io") as (a, _):
        await _create(a, "One")
        resp = await a.get("/api/tenants/current/members", headers={"X-Tenant-ID": "x" * 60})
        assert resp.status_code == 403
