"""Bounded, tenant-scoped member pages with stable ordering and complete traversal."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from tenants.models import Membership, Tenant
from tenants.web.endpoints.api import router


async def test_members_api_and_page_paginate_and_clamp(app, tenant_client):
    async with tenant_client("owner") as (client, tenant_id, owner_id):
        async with app.state.sm.db.session_factory() as db:
            owner = await db.scalar(
                select(Membership).where(
                    Membership.tenant_id == tenant_id, Membership.user_id == owner_id
                )
            )
            # Use a tied timestamp so the primary-key tie breaker matters.
            joined = datetime(2026, 1, 1, tzinfo=UTC)
            assert owner is not None
            owner.created_at = joined
            foreign = Tenant(name="Foreign", slug="foreign")
            db.add(foreign)
            await db.flush()
            for i in range(59):
                db.add(Membership(tenant_id=tenant_id, user_id=f"member-{i}", created_at=joined))
            db.add(Membership(tenant_id=foreign.id, user_id="outsider"))
            await db.commit()

        pages = []
        for page in (1, 2, 3):
            response = await client.get(f"/api/tenants/current/members?page={page}")
            assert response.status_code == 200
            data = response.json()
            assert (data["total"], data["page"], data["per_page"], data["pages"]) == (
                60,
                page,
                25,
                3,
            )
            pages.extend(m["user_id"] for m in data["items"])
        assert pages == [owner_id, *[f"member-{i}" for i in range(59)]]
        props = (
            await client.get("/tenants/members?page=99&per_page=10", headers={"X-Inertia": "true"})
        ).json()["props"]
        assert props["pagination"] == {"page": 6, "per_page": 10, "total": 60}
        assert len(props["members"]) == 10
        # Removing the final page's last member must return the previous valid page.
        last = (await client.get("/api/tenants/current/members?page=60&per_page=1")).json()[
            "items"
        ][0]
        assert (
            await client.delete(f"/api/tenants/current/members/{last['user_id']}")
        ).status_code == 204
        data = (await client.get("/api/tenants/current/members?page=60&per_page=1")).json()
        assert (data["page"], data["total"]) == (59, 59)


@pytest.mark.parametrize("query", ["page=0", "page=oops", "per_page=0", "per_page=201"])
async def test_members_api_rejects_invalid_pagination(tenant_client, query):
    async with tenant_client("owner") as (client, _, _):
        assert (await client.get(f"/api/tenants/current/members?{query}")).status_code == 422


async def test_empty_roster_and_lenient_page_parameters(app, tenant_client):
    async with tenant_client("owner") as (client, tenant_id, _):
        props = (
            await client.get(
                "/tenants/members?page=oops&per_page=-1", headers={"X-Inertia": "true"}
            )
        ).json()["props"]
        assert props["pagination"] == {"page": 1, "per_page": 1, "total": 1}
        # Keep the already-authorized request's membership cache warm to exercise
        # an empty roster independently of the tenant access gate.
        async with app.state.sm.db.session_factory() as db:
            await db.execute(delete(Membership).where(Membership.tenant_id == tenant_id))
            await db.commit()
        data = (await client.get("/api/tenants/current/members?page=999")).json()
        assert data == {"items": [], "total": 0, "page": 1, "per_page": 25, "pages": 1}


def test_members_openapi_preserves_typed_items():
    application = FastAPI()
    application.include_router(router)
    schema = application.openapi()
    response = schema["paths"]["/current/members"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    model = schema["components"]["schemas"][response["$ref"].split("/")[-1]]
    assert model["properties"]["items"]["items"] == {"$ref": "#/components/schemas/MemberView"}
