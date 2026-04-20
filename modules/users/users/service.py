"""UserService — admin operations delegating to the DB and UserManager."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.contracts.schemas import UserCreate, UserListItem
from users.exceptions import UserNotFoundError
from users.manager import UserManager
from users.models import Role, User, UserRole


class UserService:
    def __init__(
        self,
        db: AsyncSession,
        user_manager: UserManager,
    ) -> None:
        self._db = db
        self._manager = user_manager

    # ── Helpers ─────────────────────────────────────────────────

    async def _resolve_roles(self, role_names: list[str]) -> list[Role]:
        """Return Role ORM objects matching the given names."""
        if not role_names:
            return []
        result = await self._db.execute(select(Role).where(Role.name.in_(role_names)))
        return list(result.scalars().all())

    async def to_list_item(self, user: User) -> UserListItem:
        """Build the DTO from a User with roles already eager-loaded."""
        return UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            disabled_at=user.disabled_at,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            roles=[r.name for r in user.roles],
        )

    async def _get_user_with_roles(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        return result.scalar_one_or_none()

    async def _require_user(self, user_id: uuid.UUID) -> User:
        """Fetch a user with roles eager-loaded, or raise UserNotFoundError."""
        user = await self._get_user_with_roles(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    # ── Public API ───────────────────────────────────────────────

    async def list_users(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: str | None = None,
        status: str | None = None,
        role_name: str | None = None,
        verified: str | None = None,
        sort: str = "email",
        order: str = "asc",
    ) -> tuple[list[UserListItem], int]:
        """Returns (items, total_count).

        Filters: search (email/full_name LIKE), status ("active"|"disabled"),
        role_name (string), verified ("yes"|"no").
        Sort: email|last_login_at|created_at, asc|desc.
        last_login_at always uses NULLS LAST regardless of direction.
        """
        stmt = select(User).options(selectinload(User.roles))
        count_stmt = select(func.count()).select_from(User)

        conditions = []

        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(
                    User.email.ilike(pattern),
                    User.full_name.ilike(pattern),
                )
            )

        if status == "active":
            conditions.append(User.is_active.is_(True))
        elif status == "disabled":
            conditions.append(User.is_active.is_(False))

        if verified == "yes":
            conditions.append(User.is_verified.is_(True))
        elif verified == "no":
            conditions.append(User.is_verified.is_(False))

        if role_name is not None:
            subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role_name)
            )
            conditions.append(User.id.in_(subq))

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self._db.execute(count_stmt)).scalar_one()

        sort_col_map = {
            "email": User.email,
            "last_login_at": User.last_login_at,
            "created_at": User.created_at,
        }
        sort_col = sort_col_map.get(sort, User.email)

        if sort == "last_login_at":
            order_clause = (
                sort_col.desc().nulls_last()  # type: ignore[union-attr]
                if order == "desc"
                else sort_col.asc().nulls_last()  # type: ignore[union-attr]
            )
        else:
            order_clause = (
                sort_col.desc() if order == "desc" else sort_col.asc()  # type: ignore[union-attr]
            )

        stmt = stmt.order_by(order_clause).offset((page - 1) * per_page).limit(per_page)
        rows = (await self._db.execute(stmt)).scalars().all()

        items = [await self.to_list_item(u) for u in rows]
        return items, total

    async def invite(
        self,
        email: str,
        full_name: str | None,
        role_names: list[str],
        *,
        invited_by: User | None = None,
    ) -> tuple[User, str]:
        """Creates unverified user + random unusable password, assigns roles,
        mints a verification token. Returns (user, token)."""
        password = secrets.token_urlsafe(32)
        user_create = UserCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_active=True,
            is_verified=False,
        )
        user = await self._manager.create(user_create, safe=False)

        # Assign roles
        roles = await self._resolve_roles(role_names)
        invited_by_str = str(invited_by.id) if invited_by else None
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=invited_by_str,
                )
            )
        if roles:
            await self._db.flush()
            await self._db.refresh(user, attribute_names=["roles"])

        token = await self._manager.generate_verification_token(user)
        return user, token

    async def disable(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        user.disabled_at = datetime.now(UTC)
        user.is_active = False
        await self._db.flush()
        return user

    async def enable(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        user.disabled_at = None
        user.is_active = True
        await self._db.flush()
        return user

    async def set_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        *,
        assigned_by: str | None = None,
    ) -> User:
        user = await self._require_user(user_id)

        # Delete all existing role assignments for this user
        await self._db.execute(delete(UserRole).where(UserRole.user_id == user_id))

        # Insert new role assignments
        roles = await self._resolve_roles(role_names)
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user_id,
                    role_id=role.id,
                    assigned_by=assigned_by,
                )
            )

        await self._db.flush()
        await self._db.refresh(user, attribute_names=["roles"])
        return user

    async def generate_reset_link(self, user_id: uuid.UUID, base_url: str) -> str:
        """Build an admin-copyable password-reset URL. No email side-effect."""
        user = await self._require_user(user_id)

        token = await self._manager.generate_reset_password_token(user)
        return f"{base_url.rstrip('/')}/users/reset-password?token={token}"

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        return await self._get_user_with_roles(user_id)

    async def get_list_item(self, user_id: uuid.UUID) -> UserListItem:
        user = await self._require_user(user_id)
        return await self.to_list_item(user)
