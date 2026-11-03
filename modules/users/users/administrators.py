"""The shared definition of an available local administrator."""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.constants import ADMIN_ROLE_NAME
from users.models import Role, User, UserRole


async def count_active_administrators(
    session: AsyncSession, *, excluding: uuid.UUID | None = None
) -> int:
    """Count active, enabled superusers or holders of the Admin role."""
    admin_ids = (
        select(UserRole.user_id)
        .join(Role, col(Role.id) == UserRole.role_id)
        .where(Role.name == ADMIN_ROLE_NAME)
    )
    query = (
        select(func.count())
        .select_from(User)
        .where(
            col(User.is_active).is_(True),
            col(User.disabled_at).is_(None),
            or_(col(User.is_superuser).is_(True), col(User.id).in_(admin_ids)),
        )
    )
    if excluding is not None:
        query = query.where(col(User.id) != excluding)
    return (await session.scalar(query)) or 0
