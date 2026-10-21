"""The audit log as the core activity feed the users edit page reads (GH #501)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from audit_log.activity import AuditActivityFeed
from audit_log.models import AuditEntry
from simple_module_core.activity_feed import get_activity_feed
from simple_module_core.audit_links import AuditLink, AuditLinkRegistry
from simple_module_core.permissions import WILDCARD

_GATE = "secrets.view"


async def test_audit_log_installs_the_feed(app):
    assert isinstance(get_activity_feed(app), AuditActivityFeed)


async def test_recent_entries_by_one_actor_with_gated_labels(app):
    actor, other = str(uuid.uuid4()), str(uuid.uuid4())
    registry = AuditLinkRegistry()

    async def _names(db, ids):
        return {i: f"name-{i}" for i in ids}

    registry.register(
        AuditLink(
            entity_type="Secret", url_template="", label_resolver=_names, label_permission=_GATE
        )
    )
    registry.register(AuditLink(entity_type="Note", url_template="", label_resolver=_names))
    app_like = SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(audit_links=registry)))

    async with app.state.sm.db.session_factory() as db:
        for n, (etype, who) in enumerate([("Note", actor), ("Secret", actor), ("Note", other)]):
            db.add(
                AuditEntry(
                    entity_type=etype,
                    entity_id=f"e{n}",
                    action="updated",
                    changes=[{"field": "body"}],
                    user_id=who,
                    tenant_id="default",
                )
            )
        await db.flush()

        feed = AuditActivityFeed(app_like)
        items = await feed.recent_for_actor(db, actor, limit=10, permissions=[])
        assert sorted((i.entity_type, i.entity_label) for i in items) == [
            ("Note", "name-e0"),
            # Gated label withheld from a reader without the permission (GH #300).
            ("Secret", None),
        ]
        assert all(i.changes == [{"field": "body"}] for i in items)

        admin_view = await feed.recent_for_actor(db, actor, limit=1, permissions=[WILDCARD])
        assert len(admin_view) == 1


async def test_feed_is_installed_on_startup_and_cleared_on_shutdown(app):
    from audit_log.module import AuditLogModule

    assert isinstance(get_activity_feed(app), AuditActivityFeed)
    await AuditLogModule().on_shutdown(app)
    assert get_activity_feed(app) is None
    await AuditLogModule().on_startup(app)
    assert isinstance(get_activity_feed(app), AuditActivityFeed)
