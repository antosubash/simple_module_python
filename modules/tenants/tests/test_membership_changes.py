"""A membership change reaches the user's NEXT request, with no re-login (#381, #362).

``users_user.tenant_id`` used to be copied into the session at login, so moving
a user between tenants only took effect after they signed in again. The active
tenant now comes from ``tenants_membership`` on every request; these tests
keep the member's signed session cookie fixed throughout and change membership
underneath it.
"""

from __future__ import annotations


async def test_removal_takes_effect_on_the_next_request(tenant_client):
    async with (
        tenant_client() as owner,
        tenant_client("member", tenant_id=owner.tenant_id) as member,
    ):
        assert (await member.client.get("/api/tenants/current/members")).status_code == 200

        removed = await owner.client.delete(f"/api/tenants/current/members/{member.user_id}")
        assert removed.status_code == 204

        assert (await member.client.get("/api/tenants/current/members")).status_code != 200
        assert (await member.client.get("/api/tenants/")).json() == []


async def test_role_change_takes_effect_on_the_next_request(tenant_client):
    async with (
        tenant_client() as owner,
        tenant_client("member", tenant_id=owner.tenant_id) as member,
    ):
        invite = {"email": "new@example.com"}
        before = await member.client.post("/api/tenants/current/invitations", json=invite)
        assert before.status_code == 403

        promoted = await owner.client.patch(
            f"/api/tenants/current/members/{member.user_id}", json={"role": "admin"}
        )
        assert promoted.status_code == 200
        after = await member.client.post("/api/tenants/current/invitations", json=invite)
        assert after.status_code == 201

        await owner.client.patch(
            f"/api/tenants/current/members/{member.user_id}", json={"role": "member"}
        )
        demoted = await member.client.post(
            "/api/tenants/current/invitations", json={"email": "other@example.com"}
        )
        assert demoted.status_code == 403


async def test_joining_and_switching_tenants_needs_no_relogin(tenant_client):
    async with tenant_client() as user:
        first = user.tenant_id
        created = await user.client.post("/api/tenants/", json={"name": "Second", "slug": "second"})
        assert created.status_code == 201
        second = created.json()["id"]

        mine = {t["id"] for t in (await user.client.get("/api/tenants/")).json()}
        assert mine == {first, second}

        assert (await user.client.post(f"/api/tenants/{first}/switch")).status_code == 204
        members = (await user.client.get("/api/tenants/current/members")).json()
        assert [m["user_id"] for m in members] == [user.user_id]
