"""End to end: resolver → TenantMiddleware → strict query filter."""

from __future__ import annotations

import pytest
from fastapi import Depends, Request
from simple_module_db import MultiTenantMixin, create_module_base
from simple_module_db.deps import get_db
from sqlalchemy import select
from sqlmodel import Field
from tenants.contracts.events import MembershipAdded, TenantCreated

_Base = create_module_base("tenantse2e")


class _Note(_Base, MultiTenantMixin, table=True):  # ty: ignore[unsupported-base]
    __tablename__ = "tenantse2e_note"
    id: int | None = Field(default=None, primary_key=True)
    body: str = Field(max_length=100)


@pytest.fixture
async def notes_app(app):
    async with app.state.sm.db.engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    async def add_note(payload: dict, db=Depends(get_db)):
        db.add(_Note(body=payload["body"]))
        await db.flush()
        return {"ok": True}

    async def list_notes(request: Request, db=Depends(get_db)):
        rows = (await db.execute(select(_Note))).scalars().all()
        return [{"body": n.body, "tenant_id": n.tenant_id} for n in rows]

    app.add_api_route("/api/e2e/notes", add_note, methods=["POST"])
    app.add_api_route("/api/e2e/notes", list_notes, methods=["GET"])
    app.add_api_route("/e2e/notes", list_notes, methods=["GET"])
    return app


async def _org(client, name):
    return (await client.post("/api/tenants/", json={"name": name})).json()


async def test_each_tenant_sees_only_its_rows(notes_app, user_client):
    async with user_client("a@x.io") as (a, _), user_client("b@x.io") as (b, _):
        ta = await _org(a, "Alpha")
        tb = await _org(b, "Beta")
        assert (await a.post("/api/e2e/notes", json={"body": "a1"})).status_code == 200
        assert (await b.post("/api/e2e/notes", json={"body": "b1"})).status_code == 200

        assert (await a.get("/api/e2e/notes")).json() == [{"body": "a1", "tenant_id": ta["id"]}]
        assert (await b.get("/api/e2e/notes")).json() == [{"body": "b1", "tenant_id": tb["id"]}]


async def test_switching_changes_the_visible_data(notes_app, user_client):
    async with user_client("a@x.io") as (a, _):
        one = await _org(a, "One")
        await a.post("/api/e2e/notes", json={"body": "in-one"})
        await _org(a, "Two")  # creating switches to it
        assert (await a.get("/api/e2e/notes")).json() == []
        await a.post(f"/api/tenants/{one['id']}/switch")
        assert [n["body"] for n in (await a.get("/api/e2e/notes")).json()] == ["in-one"]


async def test_no_tenant_fails_closed(notes_app, user_client):
    async with user_client("nobody@x.io") as (client, _):
        api = await client.get("/api/e2e/notes")
        assert api.status_code == 403
        assert api.json()["detail"] == "tenant_required"
        page = await client.get("/e2e/notes")
        assert page.status_code == 303
        assert page.headers["location"].startswith("/tenants?reason=tenant_required")


async def test_removed_member_loses_access_immediately(notes_app, user_client):
    async with user_client("o@x.io") as (owner, _), user_client("m@x.io") as (member, member_id):
        await _org(owner, "Acme")
        token = (
            await owner.post("/api/tenants/current/invitations", json={"email": "m@x.io"})
        ).json()["token"]
        await member.post("/api/tenants/invitations/accept", json={"token": token})
        await owner.post("/api/e2e/notes", json={"body": "secret"})
        assert len((await member.get("/api/e2e/notes")).json()) == 1

        assert (await owner.delete(f"/api/tenants/current/members/{member_id}")).status_code == 204
        assert (await member.get("/api/e2e/notes")).status_code == 403


async def test_suspended_tenant_is_not_resolved(notes_app, user_client, authenticated_client):
    async with user_client("o@x.io") as (owner, _):
        tenant = await _org(owner, "Late Payer")
        assert (await owner.get("/api/e2e/notes")).status_code == 200

        resp = await authenticated_client.post(f"/api/tenants/admin/{tenant['id']}/suspend")
        assert resp.status_code == 200 and resp.json()["status"] == "suspended"
        assert (await owner.get("/api/e2e/notes")).status_code == 403
        page = await owner.get("/tenants/", headers={"X-Inertia": "true"})
        assert page.json()["props"]["suspended"] is True

        await authenticated_client.post(f"/api/tenants/admin/{tenant['id']}/reactivate")
        assert (await owner.get("/api/e2e/notes")).status_code == 200


async def test_events_fire_after_commit(app, user_client):
    seen: list = []

    async def record(event):
        seen.append(event)

    app.state.sm.event_bus.subscribe(TenantCreated, record)
    app.state.sm.event_bus.subscribe(MembershipAdded, record)
    async with user_client("o@x.io") as (owner, _):
        tenant = await _org(owner, "Evented")
    kinds = {(type(e).__name__, e.tenant_id) for e in seen}
    assert ("TenantCreated", tenant["id"]) in kinds
    assert ("MembershipAdded", tenant["id"]) in kinds


async def test_shared_prop_lists_memberships(user_client):
    async with user_client("o@x.io") as (owner, _):
        tenant = await _org(owner, "Shared")
        page = await owner.get("/tenants/", headers={"X-Inertia": "true"})
        shared = page.json()["props"]["tenant"]
        assert shared["active"]["id"] == tenant["id"]
        assert [m["id"] for m in shared["memberships"]] == [tenant["id"]]
