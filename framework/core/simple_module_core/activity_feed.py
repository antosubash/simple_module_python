"""The activity feed: "what has this person done lately", without the audit log.

The users edit page shows a card of the account's recent actions. The audit log
is what records them, but ``users`` must not import ``audit_log`` (and
``audit_log`` must not import ``users``): each is optional to the other, and
importing both ways was a cycle (GH #501).

So ``audit_log`` registers an :class:`ActivityFeed` with
:func:`set_activity_feed` and the card asks :func:`get_activity_feed`. ``None``
means nothing records activity on this install — a card that is absent, which
is a different claim from an empty one ("nobody did anything").
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

ACTIVITY_FEED_STATE_ATTR = "activity_feed"
"""``app.state`` attribute holding the active :class:`ActivityFeed`."""


@dataclass(frozen=True)
class ActivityItem:
    """One thing an actor did."""

    at: datetime
    action: str
    entity_type: str
    entity_id: str
    #: The row's display name, when its owner can name it and the reader may
    #: see that name; ``None`` otherwise (the caller shows a short id).
    entity_label: str | None = None
    #: The recorded change set, whatever its shape, for summarising which
    #: fields moved. ``None`` when the recorder kept none.
    changes: Any = None


@runtime_checkable
class ActivityFeed(Protocol):
    async def recent_for_actor(
        self,
        db: Any,
        actor_id: str,
        *,
        limit: int,
        permissions: Collection[str],
    ) -> list[ActivityItem]:
        """The latest *limit* actions by *actor_id*, newest first.

        *permissions* are the reader's grants: labels whose owner gated them
        behind a permission the reader lacks come back as ``None``.
        """
        ...


def set_activity_feed(app: Any, feed: ActivityFeed | None) -> None:
    """Install (or, with ``None``, remove) the app's activity feed."""
    setattr(app.state, ACTIVITY_FEED_STATE_ATTR, feed)


def get_activity_feed(app: Any) -> ActivityFeed | None:
    """The app's activity feed, or ``None`` when nothing records activity."""
    return getattr(app.state, ACTIVITY_FEED_STATE_ATTR, None)


__all__ = [
    "ACTIVITY_FEED_STATE_ATTR",
    "ActivityFeed",
    "ActivityItem",
    "get_activity_feed",
    "set_activity_feed",
]
