"""Audit rows record how the actor authenticated and, for tokens, which one (#1178)."""

from __future__ import annotations

import uuid

from _api_tokens_support import CSRF, create_pat, join_tenant, make_admin
from audit_log.models import AuditEntry
from simple_module_db.auditing._bulk_audit_records import ACTION_BULK_UPDATED
from simple_module_db.auditing.bulk_audit import record_bulk_audit
from simple_module_db.models.credential import current_auth_kind, current_token_id
from simple_module_test.web.tenant_client import session_client
from sqlmodel import col, select
from tenants.core.constants import SESSION_ACTIVE_TENANT, Permissions

_URL = "/api/tenants/"


async def _tenant_rows(app, name: str) -> list[AuditEntry]:
    async with app.state.sm.db.session_factory() as session:
        stmt = select(AuditEntry).where(col(AuditEntry.entity_type) == "Tenant")
        rows = (await session.execute(stmt)).scalars().all()
    return [r for r in rows if any(c.get("new") == name for c in r.changes)]


async def _admin(app) -> tuple[str, str]:
    email = f"adm-{uuid.uuid4().hex[:8]}@example.com"
    user_id = await make_admin(app, email)
    return user_id, await join_tenant(app, user_id, email)


async def test_pat_mutation_records_pat_and_token_id(app):
    import httpx

    user_id, tenant_id = await _admin(app)
    data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
    async with session_client(app, data) as c:
        body = await create_pat(c, [Permissions.PLATFORM_MANAGE])
    app.state.tenants.settings.allow_self_service = False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {body['token']}"},
    ) as bc:
        resp = await bc.post(_URL, json={"name": "Attr Pat"})
    assert resp.status_code == 201, resp.text
    rows = await _tenant_rows(app, "Attr Pat")
    assert rows
    assert {r.auth_kind for r in rows} == {"pat"}
    assert {r.token_id for r in rows} == {str(body["item"]["id"])}


async def test_session_mutation_records_session_without_token(app):
    user_id, tenant_id = await _admin(app)
    data = {"user_id": user_id, SESSION_ACTIVE_TENANT: tenant_id, "sm_csrf_token": CSRF}
    app.state.tenants.settings.allow_self_service = True
    async with session_client(app, data) as c:
        resp = await c.post(_URL, json={"name": "Attr Session"}, headers={"X-CSRF-Token": CSRF})
    assert resp.status_code == 201, resp.text
    rows = await _tenant_rows(app, "Attr Session")
    assert rows
    assert {r.auth_kind for r in rows} == {"session"}
    assert {r.token_id for r in rows} == {None}


async def test_bulk_record_carries_credential(app):
    kind = current_auth_kind.set("service")
    tok = current_token_id.set("tok-1")
    try:
        async with app.state.sm.db.session_factory() as session:
            record_bulk_audit(session, "AttrBulk", ACTION_BULK_UPDATED, ["1"], {"x": 1})
            await session.commit()
    finally:
        current_token_id.reset(tok)
        current_auth_kind.reset(kind)
    async with app.state.sm.db.session_factory() as session:
        stmt = select(AuditEntry).where(col(AuditEntry.entity_type) == "AttrBulk")
        rows = (await session.execute(stmt)).scalars().all()
    assert [(r.auth_kind, r.token_id) for r in rows] == [("service", "tok-1")]


async def test_audit_api_returns_fields(app, authenticated_client):
    async with app.state.sm.db.session_factory() as session:
        session.add(
            AuditEntry(
                entity_type="AttrApi",
                entity_id="1",
                action="updated",
                auth_kind="pat",
                token_id="tok-9",
            )
        )
        await session.commit()
    resp = await authenticated_client.get("/api/audit_log/", params={"entity_type": "AttrApi"})
    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert (item["auth_kind"], item["token_id"]) == ("pat", "tok-9")
