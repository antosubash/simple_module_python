"""AuditEntry carries the tenant of the write that produced it (#372).

The table is not tenant-scoped: platform writes have no tenant (NULL), and the
admin screens read across tenants with a tenant filter.
"""

from __future__ import annotations

import csv
import io

import pytest
from audit_log.capture import audit_callback
from audit_log.constants import PLATFORM_TENANT_FILTER
from audit_log.models import AuditEntry
from simple_module_core.tenancy import TenantRole
from simple_module_db import all_tenants, tenant_context
from simple_module_db.audit import AuditRecord
from sqlalchemy import select

LIST_URL = "/api/audit_log/"
EXPORT_URL = "/api/audit_log/export.csv"
_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


def _record(entity_id: str) -> AuditRecord:
    return AuditRecord(
        entity_type="Widget",
        entity_id=entity_id,
        action="created",
        changes=[],
        user_id=None,
        correlation_id=None,
    )


async def _entry(db_session, entity_id: str) -> AuditEntry:
    with all_tenants():
        return (
            await db_session.execute(select(AuditEntry).where(AuditEntry.entity_id == entity_id))
        ).scalar_one()


async def test_capture_stamps_current_tenant(db_session):
    with tenant_context("tenant-a"):
        audit_callback(db_session.sync_session, [_record("w1")])
        await db_session.flush()
    assert (await _entry(db_session, "w1")).tenant_id == "tenant-a"


async def test_platform_write_has_null_tenant(db_session):
    audit_callback(db_session.sync_session, [_record("w2")])
    await db_session.flush()
    assert (await _entry(db_session, "w2")).tenant_id is None

    with all_tenants():
        audit_callback(db_session.sync_session, [_record("w3")])
        await db_session.flush()
    assert (await _entry(db_session, "w3")).tenant_id is None


@pytest.fixture
async def seeded(app):
    async with app.state.sm.db.session_factory() as session:
        for tenant, n in (("tenant-a", 2), ("tenant-b", 1), (None, 1)):
            for i in range(n):
                session.add(
                    AuditEntry(
                        entity_type="Widget",
                        entity_id=f"{tenant}-{i}",
                        action="created",
                        changes=[],
                        tenant_id=tenant,
                    )
                )
        await session.commit()


async def test_list_filter_by_tenant(authenticated_client, seeded):
    resp = await authenticated_client.get(LIST_URL, params={"tenant_id": "tenant-a"})
    body = resp.json()
    assert body["total"] == 2
    assert {i["tenant_id"] for i in body["items"]} == {"tenant-a"}

    # Platform entries (NULL) include the admin seeding, so only assert shape.
    resp = await authenticated_client.get(
        LIST_URL, params={"tenant_id": PLATFORM_TENANT_FILTER, "page_size": 200}
    )
    items = resp.json()["items"]
    assert {i["tenant_id"] for i in items} == {None}
    assert "None-0" in {i["entity_id"] for i in items}

    resp = await authenticated_client.get(LIST_URL, params={"entity_type": "Widget"})
    assert resp.json()["total"] == 4  # unfiltered stays platform-wide


async def test_export_filters_and_lists_tenant(authenticated_client, seeded):
    resp = await authenticated_client.get(EXPORT_URL, params={"tenant_id": "tenant-b"})
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert [r["tenant_id"] for r in rows] == ["tenant-b"]

    resp = await authenticated_client.get(EXPORT_URL)
    tenants = {r["tenant_id"] for r in csv.DictReader(io.StringIO(resp.text))}
    assert {"tenant-a", "tenant-b", ""} <= tenants


async def test_browse_view_exposes_tenant_ids(authenticated_client, seeded):
    resp = await authenticated_client.get(
        "/admin/audit-log/", params={"tenant_id": "tenant-a"}, headers=_INERTIA
    )
    props = resp.json()["props"]
    assert {"tenant-a", "tenant-b"} <= set(props["tenant_ids"])
    assert props["total"] == 2
    assert props["filters"]["tenant_id"] == "tenant-a"


@pytest.mark.parametrize("role", list(TenantRole))
async def test_tenant_member_cannot_read_audit_log(tenant_client, role):
    async with tenant_client(role) as m:
        assert (await m.client.get(LIST_URL)).status_code == 403
        assert (await m.client.get(EXPORT_URL)).status_code == 403
