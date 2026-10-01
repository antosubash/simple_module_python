"""Regressions from the tenancy QA pass (adversarial + browser)."""

from __future__ import annotations

import asyncio

from simple_module_test.fixtures import SETUP_ADMIN_EMAIL
from tenants import resolver
from tenants.service import TenantService


async def _org(client, name: str) -> dict:
    return (await client.post("/api/tenants/", json={"name": name})).json()


async def _invite(owner, member, email: str, role: str = "member") -> None:
    token = (
        await owner.post("/api/tenants/current/invitations", json={"email": email, "role": role})
    ).json()["token"]
    assert (
        await member.post("/api/tenants/invitations/accept", json={"token": token})
    ).status_code == 200


async def test_invite_link_ignores_the_host_header(user_client):
    async with user_client("o@x.io") as (owner, _):
        await _org(owner, "Acme")
        resp = await owner.post(
            "/api/tenants/current/invitations",
            json={"email": "n@x.io"},
            headers={"Host": "evil.example"},
        )
        assert resp.json()["accept_url"].startswith("/tenants/invitations/accept?token=")


async def test_invite_link_uses_the_configured_origin(app, user_client):
    app.state.tenants.settings.public_base_url = "https://app.example.com/"
    try:
        async with user_client("o@x.io") as (owner, _):
            await _org(owner, "Acme")
            resp = await owner.post("/api/tenants/current/invitations", json={"email": "n@x.io"})
            assert resp.json()["accept_url"].startswith("https://app.example.com/tenants/")
    finally:
        app.state.tenants.settings.public_base_url = ""


async def test_platform_admin_who_is_a_plain_member_cannot_manage(
    user_client, authenticated_client
):
    async with user_client("o@x.io") as (owner, owner_id):
        await _org(owner, "Acme")
        # The platform admin (wildcard permissions) joins as a plain member.
        token = (
            await owner.post("/api/tenants/current/invitations", json={"email": SETUP_ADMIN_EMAIL})
        ).json()["token"]
        await authenticated_client.post("/api/tenants/invitations/accept", json={"token": token})
        resp = await authenticated_client.delete(f"/api/tenants/current/members/{owner_id}")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "tenant_manager_required"


async def test_cannot_accept_into_a_suspended_tenant(user_client, authenticated_client):
    async with user_client("o@x.io") as (owner, _), user_client("n@x.io") as (new, _):
        tenant = await _org(owner, "Late")
        token = (
            await owner.post("/api/tenants/current/invitations", json={"email": "n@x.io"})
        ).json()["token"]
        await authenticated_client.post(f"/api/tenants/admin/{tenant['id']}/suspend")
        resp = await new.post("/api/tenants/invitations/accept", json={"token": token})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "tenant_suspended"


async def test_cannot_invite_an_existing_member(user_client):
    async with user_client("o@x.io") as (owner, _), user_client("m@x.io") as (member, _):
        await _org(owner, "Acme")
        await _invite(owner, member, "m@x.io")
        resp = await owner.post("/api/tenants/current/invitations", json={"email": "M@x.io"})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "already_member"


async def test_suspended_active_org_is_not_switched_away_silently(
    user_client, authenticated_client
):
    async with user_client("o@x.io") as (owner, _):
        acme = await _org(owner, "Acme")
        globex = await _org(owner, "Globex")
        await owner.post(f"/api/tenants/{acme['id']}/switch")
        await authenticated_client.post(f"/api/tenants/admin/{acme['id']}/suspend")
        props = (await owner.get("/tenants/", headers={"X-Inertia": "true"})).json()["props"]
        assert props["active_id"] == globex["id"]
        assert props["suspended"] is True
        assert props["suspended_name"] == "Acme"


async def test_inflight_read_does_not_recache_a_removed_member(app, monkeypatch):
    """F5: a read that started before an invalidation must not store its result."""
    resolver.forget(None)
    started, release = asyncio.Event(), asyncio.Event()
    real = TenantService.list_for_user

    async def slow(self, user_id):
        rows = await real(self, user_id)
        started.set()
        await release.wait()
        return rows

    monkeypatch.setattr(TenantService, "list_for_user", slow)
    read = asyncio.create_task(resolver.memberships_for(app, "u-1"))
    await started.wait()
    resolver.forget("u-1")  # the membership changed while the read was in flight
    release.set()
    await read
    assert resolver.cached_memberships("u-1") is None


async def test_slug_shape_is_enforced(user_client):
    async with user_client("o@x.io") as (owner, _):
        for bad in ["ABC", "-abc", "abc-", "a" * 51, "a/b", "ab c"]:
            resp = await owner.post("/api/tenants/", json={"name": "X", "slug": bad})
            assert resp.status_code == 422, bad
        ok = await owner.post("/api/tenants/", json={"name": "X", "slug": "a-b-1"})
        assert ok.status_code == 201


async def test_concurrent_accepts_of_one_invitation_give_200_and_409(user_client):
    async with user_client("o@x.io") as (owner, _), user_client("n@x.io") as (new, _):
        await _org(owner, "Acme")
        token = (
            await owner.post("/api/tenants/current/invitations", json={"email": "n@x.io"})
        ).json()["token"]
        results = await asyncio.gather(
            new.post("/api/tenants/invitations/accept", json={"token": token}),
            new.post("/api/tenants/invitations/accept", json={"token": token}),
        )
        assert sorted(r.status_code for r in results) == [200, 409]
