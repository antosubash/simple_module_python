"""Target-user filtering is about ownership, independently of the actor (#1166)."""

import csv
import io
import uuid
from collections import Counter

import pytest
from audit_log.models import AuditEntry
from users.models import OAuthAccount, User

_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}
_CORRELATION = "target-filter-test"


@pytest.fixture
async def target_entries(app):
    target, other = uuid.uuid4(), uuid.uuid4()
    live, deleted = uuid.uuid4(), uuid.uuid4()
    role_id = str((target, uuid.uuid4()))
    rows = [
        ("user", "User", str(target), [], "tenant-a"),
        ("live", "OAuthAccount", str(live), [], "tenant-a"),
        (
            "created-link",
            "OAuthAccount",
            str(deleted),
            [{"field": "user_id", "new": str(target)}],
            "tenant-a",
        ),
        ("deleted-link", "OAuthAccount", str(deleted), [], "tenant-a"),
        ("role", "UserRole", role_id, [], "tenant-a"),
        ("other-tenant", "User", str(target), [], "tenant-b"),
        ("actor-only", "User", str(other), [], "tenant-a"),
        ("wrong-kind", "Unrelated", str(target), [], "tenant-a"),
        # A role id equal to the target is not an assignment to that user.
        ("wrong-role", "UserRole", str((other, target)), [], "tenant-a"),
    ]
    ids, refs = {}, {}
    async with app.state.sm.db.session_factory() as db:
        for uid in (target, other):
            db.add(User(id=uid, email=f"{uid}@example.com", hashed_password="unused"))
        await db.flush()
        db.add(
            OAuthAccount(
                id=live,
                user_id=target,
                oauth_name="test",
                access_token="unused",
                account_id="live",
                account_email="test@example.com",
            )
        )
        for name, kind, entity_id, changes, tenant in rows:
            row = AuditEntry(
                entity_type=kind,
                entity_id=entity_id,
                action="updated",
                changes=changes,
                user_id=str(target if name == "actor-only" else other),
                tenant_id=tenant,
                correlation_id=_CORRELATION,
            )
            ids[name] = str(row.id)
            refs[name] = (kind, entity_id)
            db.add(row)
        await db.commit()
    return str(target), str(other), ids, refs


async def _read(client, route, params):
    response = await client.get(route, params=params, headers=_INERTIA)
    assert response.status_code == 200, response.text
    if route.endswith("export.csv"):
        return list(csv.DictReader(io.StringIO(response.text))), None
    body = response.json()
    props = body.get("props", body)
    return props["items"], props


@pytest.mark.parametrize(
    "route",
    [
        "/api/audit_log/",
        "/admin/audit-log/",
        "/api/audit_log/export.csv",
    ],
)
async def test_target_user_includes_linked_and_deleted_entities(
    authenticated_client,
    target_entries,
    route,
):
    target, _, ids, refs = target_entries
    items, props = await _read(
        authenticated_client,
        route,
        {
            "target_user_id": target,
            "correlation_id": _CORRELATION,
        },
    )
    included = ("user", "live", "created-link", "deleted-link", "role", "other-tenant")
    assert Counter((item["entity_type"], item["entity_id"]) for item in items) == Counter(
        refs[key] for key in included
    )
    if props:
        assert {item["id"] for item in items} == {ids[key] for key in included}
        assert props["total"] == 6
        if "filters" in props:
            assert props["filters"]["target_user_id"] == target


@pytest.mark.parametrize("route", ["/api/audit_log/", "/admin/audit-log/"])
async def test_target_user_combines_with_actor_and_tenant(
    authenticated_client,
    target_entries,
    route,
):
    target, other, ids, _ = target_entries
    params = {"target_user_id": target, "correlation_id": _CORRELATION, "tenant_id": "tenant-b"}
    items, _ = await _read(authenticated_client, route, {**params, "user_id": other})
    assert [item["id"] for item in items] == [ids["other-tenant"]]
    items, _ = await _read(authenticated_client, route, {**params, "user_id": target})
    assert items == []
    items, _ = await _read(
        authenticated_client,
        route,
        {
            "user_id": target,
            "correlation_id": _CORRELATION,
        },
    )
    assert [item["id"] for item in items] == [ids["actor-only"]]


@pytest.mark.parametrize("target", ["not-a-uuid", str(uuid.UUID(int=0))])
async def test_unmatched_target_does_not_widen_results(
    authenticated_client, target_entries, target
):
    items, props = await _read(
        authenticated_client,
        "/api/audit_log/",
        {
            "target_user_id": target,
            "correlation_id": _CORRELATION,
        },
    )
    assert items == []
    assert props["total"] == 0
