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


@pytest.mark.parametrize("may_name_users", [True, False])
async def test_target_label_obeys_user_label_permission(monkeypatch, may_name_users):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from audit_log.web.endpoints import views
    from simple_module_core.web.audit_links import AuditLink, AuditLinkRegistry
    from users.core.directory import UsersDirectory

    target = str(uuid.UUID(int=1))
    labels = AsyncMock(return_value={target: "target@example.com"})
    links = AuditLinkRegistry()
    links.register(
        AuditLink(
            entity_type="User",
            url_template="",
            label_resolver=labels,
            label_permission="users.manage",
        )
    )
    db = SimpleNamespace(bind=SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    service = SimpleNamespace(
        db=db,
        list_filtered=AsyncMock(
            return_value=SimpleNamespace(items=[], total=0, page=1, page_size=50)
        ),
        distinct_entity_types=AsyncMock(return_value=[]),
        distinct_tenant_ids=AsyncMock(return_value=[]),
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                sm=SimpleNamespace(audit_links=links), user_directory=UsersDirectory()
            )
        )
    )
    monkeypatch.setattr(
        views, "resolved_permissions_for", lambda _: {"users.manage"} if may_name_users else set()
    )
    rendered: dict = {}

    async def render(_page: str, page_props: dict) -> dict:
        rendered.update(page_props)
        return page_props

    await views.browse(
        request=request,
        inertia=SimpleNamespace(render=render),
        service=service,
        translator=SimpleNamespace(t=lambda key: key),
        db=db,
        entity_type=None,
        entity_id=None,
        action=None,
        user_id=None,
        target_user_id=target,
        correlation_id=None,
        tenant_id=None,
        from_date=None,
        to_date=None,
        page=None,
        page_size=None,
    )
    props = rendered
    assert props.get("target_user_label") == ("target@example.com" if may_name_users else None)
    assert props["filters"]["target_user_id"] == target
    if not may_name_users:
        labels.assert_not_called()


def test_bulk_summaries_do_not_share_ownership():
    from audit_log.entries.target_user import target_user_filter
    from simple_module_core.web.audit_links import AuditLinkRegistry
    from sqlalchemy import create_engine, select
    from users.core.audit import linked_user_audit_links
    from users.core.directory import UsersDirectory

    target, other = uuid.UUID(int=1), uuid.UUID(int=2)
    registry = AuditLinkRegistry()
    for link in linked_user_audit_links():
        registry.register(link)
    engine = create_engine("sqlite://")
    AuditEntry.__table__.create(engine)
    OAuthAccount.__table__.create(engine)
    with engine.begin() as connection:
        for action, owner in [("target-summary", target), ("other-summary", other)]:
            connection.execute(
                AuditEntry.__table__.insert().values(
                    entity_type="OAuthAccount",
                    entity_id="*",
                    action=action,
                    changes=[{"field": "user_id", "new": str(owner)}],
                )
            )
        predicate = target_user_filter(registry, UsersDirectory(), str(target), "sqlite")
        assert list(connection.execute(select(AuditEntry.action).where(predicate)).scalars()) == [
            "target-summary"
        ]
    engine.dispose()
