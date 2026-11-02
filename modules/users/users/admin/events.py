"""Transactional publication of admin lifecycle events."""

from simple_module_core.events import Event, EventBus
from simple_module_db.callbacks import register_on_commit
from sqlalchemy.ext.asyncio import AsyncSession


async def publish_admin_event(bus: EventBus, event: Event, db: AsyncSession) -> None:
    await bus.publish_durable_or_inline(event, db)
    # Preserve ordinary subscribers, but only after the user write commits.
    register_on_commit(db, lambda: bus.publish(event))
