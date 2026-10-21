"""The audit log as the app's :class:`~simple_module_core.activity_feed.ActivityFeed`.

The users edit page shows what an account did lately. It asks the core
activity feed rather than importing this module (GH #501): ``users`` and
``audit_log`` are each optional to the other, and importing both ways was a
cycle. Installed in :meth:`AuditLogModule.register_settings`.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from simple_module_core.activity_feed import ActivityItem

from audit_log.resolve import resolve_entity_labels
from audit_log.service import AuditLogService


class AuditActivityFeed:
    """Recent audit entries by one actor, with their rows named."""

    def __init__(self, app: Any) -> None:
        # The app, not its registry: the audit-link registry is assembled after
        # ``register_settings`` runs, so it is read per call.
        self._app = app

    async def recent_for_actor(
        self,
        db: Any,
        actor_id: str,
        *,
        limit: int,
        permissions: Collection[str],
    ) -> list[ActivityItem]:
        page = await AuditLogService(db).list_entries(user_id=actor_id, page_size=limit)
        refs = [(entry.entity_type, entry.entity_id) for entry in page.items]
        # The reader's grants reach the resolvers, which skip entity types
        # whose owner gated their names (GH #300), exactly as the audit screen.
        labels = (
            await resolve_entity_labels(db, self._app.state.sm.audit_links, refs, permissions)
            if refs
            else {}
        )
        return [
            ActivityItem(
                at=entry.created_at,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                entity_label=labels.get((entry.entity_type, entry.entity_id)),
                changes=entry.changes,
            )
            for entry in page.items
        ]


__all__ = ["AuditActivityFeed"]
