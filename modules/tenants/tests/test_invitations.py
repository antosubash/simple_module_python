"""Invitations: issue, accept (email-bound), revoke, seat entitlements."""

from __future__ import annotations

from tenants.contracts.entitlements import UnlimitedEntitlements


class _Seats:
    def __init__(self, n: int) -> None:
        self.n = n

    async def limit(self, tenant_id: str, key: str) -> int | None:
        return self.n if key == "tenants.seats" else None

    async def has_feature(self, tenant_id: str, key: str) -> bool:
        return True


async def _setup(client) -> dict:
    return (await client.post("/api/tenants/", json={"name": "Acme"})).json()


async def test_invite_and_accept(user_client):
    async with user_client("owner@x.io") as (owner, _), user_client("new@x.io") as (new, new_id):
        tenant = await _setup(owner)
        issued = await owner.post(
            "/api/tenants/current/invitations", json={"email": "New@X.io", "role": "admin"}
        )
        assert issued.status_code == 201, issued.text
        token = issued.json()["token"]
        assert token in issued.json()["accept_url"]

        accepted = await new.post("/api/tenants/invitations/accept", json={"token": token})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["id"] == tenant["id"]
        assert accepted.json()["role"] == "admin"

        members = (await owner.get("/api/tenants/current/members")).json()
        assert {m["user_id"] for m in members} >= {new_id}

        again = await new.post("/api/tenants/invitations/accept", json={"token": token})
        assert again.status_code == 409


async def test_invitation_is_bound_to_its_email(user_client):
    async with user_client("owner@x.io") as (owner, _), user_client("thief@x.io") as (thief, _):
        await _setup(owner)
        token = (
            await owner.post("/api/tenants/current/invitations", json={"email": "friend@x.io"})
        ).json()["token"]
        resp = await thief.post("/api/tenants/invitations/accept", json={"token": token})
        assert resp.status_code == 403


async def test_invitations_cannot_grant_owner(user_client):
    async with user_client("owner@x.io") as (owner, _):
        await _setup(owner)
        resp = await owner.post(
            "/api/tenants/current/invitations", json={"email": "x@x.io", "role": "owner"}
        )
        assert resp.status_code == 422


async def test_plain_member_cannot_invite(tenant_client):
    async with tenant_client("member") as (member, _, _):
        resp = await member.post("/api/tenants/current/invitations", json={"email": "z@x.io"})
        assert resp.status_code == 403


async def test_seat_limit_blocks_invites(app, user_client):
    app.state.tenants.entitlements = _Seats(2)
    try:
        async with user_client("owner@x.io") as (owner, _):
            await _setup(owner)
            ok = await owner.post("/api/tenants/current/invitations", json={"email": "a@x.io"})
            assert ok.status_code == 201
            # owner + one pending invitation = 2 seats used
            full = await owner.post("/api/tenants/current/invitations", json={"email": "b@x.io"})
            assert full.status_code == 402
            assert full.json()["key"] == "tenants.seats"
    finally:
        app.state.tenants.entitlements = UnlimitedEntitlements()


async def test_revoked_invitation_cannot_be_accepted(user_client):
    async with user_client("owner@x.io") as (owner, _), user_client("n@x.io") as (new, _):
        await _setup(owner)
        issued = (
            await owner.post("/api/tenants/current/invitations", json={"email": "n@x.io"})
        ).json()
        assert (
            await owner.delete(f"/api/tenants/current/invitations/{issued['id']}")
        ).status_code == 204
        resp = await new.post("/api/tenants/invitations/accept", json={"token": issued["token"]})
        assert resp.status_code == 404


async def test_malformed_invite_emails_are_rejected(user_client):
    """qa BUG-003: only an "@" was checked, so junk reached the table."""
    async with user_client("owner@x.io") as (owner, _):
        await _setup(owner)
        for bad in ("a b@x.com", "@x.com", "<script>alert(1)</script>@x.com", "nodomain@", "a@b"):
            r = await owner.post("/api/tenants/current/invitations", json={"email": bad})
            assert r.status_code == 422, (bad, r.text)


async def test_open_invitation_is_unique_in_the_database(db_session):
    """The partial index itself, independent of the service pre-check."""
    from datetime import UTC, datetime, timedelta

    import pytest
    from sqlalchemy.exc import IntegrityError
    from tenants.models import Invitation, Tenant

    tenant = Tenant(name="T", slug="t-uniq")
    db_session.add(tenant)
    await db_session.flush()
    exp = datetime.now(UTC) + timedelta(days=1)
    db_session.add(Invitation(tenant_id=tenant.id, email="a@x.io", token_hash="h1", expires_at=exp))
    await db_session.flush()
    db_session.add(Invitation(tenant_id=tenant.id, email="a@x.io", token_hash="h2", expires_at=exp))
    with pytest.raises(IntegrityError):
        await db_session.flush()
