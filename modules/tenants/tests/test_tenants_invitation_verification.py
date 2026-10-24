"""A leaked invitation must not prove ownership of an unverified address (#623)."""

import uuid

from users.models import User


async def test_unverified_account_cannot_accept_invitation(app, user_client):
    app.state.users.settings.require_verification = False
    async with (
        user_client("owner@corp.com") as (owner, _),
        user_client("bob@corp.com") as (
            bob,
            bob_id,
        ),
    ):
        await owner.post("/api/tenants/", json={"name": "Corp"})
        issued = await owner.post(
            "/api/tenants/current/invitations",
            json={"email": "bob@corp.com", "role": "admin"},
        )
        assert issued.status_code == 201
        token = issued.json()["token"]
        async with app.state.sm.db.session_factory() as db:
            user = await db.get(User, uuid.UUID(bob_id))
            user.is_verified = False
            await db.commit()

        rejected = await bob.post("/api/tenants/invitations/accept", json={"token": token})
        assert rejected.status_code == 403
        members = (await owner.get("/api/tenants/current/members")).json()
        assert bob_id not in {member["user_id"] for member in members}
        pending = (await owner.get("/api/tenants/current/invitations")).json()
        assert issued.json()["id"] in {invitation["id"] for invitation in pending}

        # Rejection neither consumes the link nor grants the invited role.
        # Verification is read fresh, so the SAME session can accept once the
        # account is verified — no re-sign-in needed.
        async with app.state.sm.db.session_factory() as db:
            user = await db.get(User, uuid.UUID(bob_id))
            user.is_verified = True
            await db.commit()
        accepted = await bob.post("/api/tenants/invitations/accept", json={"token": token})
        assert accepted.status_code == 200
        assert accepted.json()["role"] == "admin"
