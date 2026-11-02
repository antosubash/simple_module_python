"""Transactional cleanup for modules that own shared resources (#683)."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete

from sharing.models import ResourceShare


async def forget_resource(
    db: AsyncSession, resource_type: str, resource_id: str | Iterable[str]
) -> None:
    """Delete shares for canonical resource ids in the caller's tenant/transaction.

    For resource owners only: no permission or resource-existence check is made.
    The caller must bind the owning tenant and commit or roll back its session.
    """
    ids = [resource_id] if isinstance(resource_id, str) else list(resource_id)
    await db.execute(
        delete(ResourceShare).where(
            col(ResourceShare.resource_type) == resource_type,
            col(ResourceShare.resource_id).in_(ids),
        )
    )
