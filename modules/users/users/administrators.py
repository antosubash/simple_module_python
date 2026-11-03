"""The shared definition of an available local administrator.

An administrator is an active, enabled holder of the Admin role. Permissions
resolve from roles only, so ``is_superuser`` on its own grants nothing: a
roleless superuser counted here would let the last account that can actually
administer the install be removed.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from users.constants import ADMIN_ROLE_NAME
from users.models import Role, User, UserRole


async def count_active_administrators(
    session: AsyncSession, *, excluding: uuid.UUID | None = None
) -> int:
    """Count active, enabled holders of the Admin role."""
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
            col(User.id).in_(admin_ids),
        )
    )
    if excluding is not None:
        query = query.where(col(User.id) != excluding)
    return (await session.scalar(query)) or 0
