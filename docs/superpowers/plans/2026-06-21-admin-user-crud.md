# Admin User CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin create, edit, and delete users directly from the `/users/admin` page (today it can only invite).

**Architecture:** Additive surface on the existing `users` module admin slice — no new module, no new tables, no migration. The over-cap `admin/service.py` is split into `admin/queries.py` (read/helpers, `class _UserServiceBase`) + `admin/service.py` (writes, `class UserService(_UserServiceBase)`), keeping the `from users.admin.service import UserService` import path unchanged. Three new service methods + three new REST endpoints + one new Inertia view route + new/updated React pages.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, fastapi-users, Inertia.js, React 19, Tailwind 4, shadcn/ui, pytest (`anyio`).

## Global Constraints

- **300-line cap** on every `.py` / `.ts` / `.tsx` file (CI: `scripts/check_file_size.py`). Split by responsibility if approaching it.
- **SQLModel only** for schemas/DTOs (plain `SQLModel` subclass) — never Pydantic `BaseModel`.
- **Service code never calls `session.commit()`** — use `await self._db.flush()`; the per-request session auto-commits on pending writes.
- **Events are `@dataclass` subclasses of `simple_module_core.events.Event`**, defined in `contracts/events.py`.
- **Admin pages use plain English strings** (no `useT()` / i18n) — matches existing `Invite.tsx` / `Edit.tsx`.
- **New endpoints stay under the existing `users.manage` permission** (the `admin_router` dependency already enforces it).
- **Route ordering:** the new view route `GET /admin/create` MUST be declared before `GET /admin/{user_id}` (FastAPI matches in declaration order), same as `/admin/invite`.
- **Verification after each backend task:** `uv run pytest modules/users/tests/<file> -v`. Final gate: `make test-py`, `make lint`, `make doctor`.

---

## File Structure

| File | Responsibility |
|---|---|
| `modules/users/users/admin/queries.py` | NEW — `_UserServiceBase`: read/query/helper methods (moved verbatim from `service.py`). |
| `modules/users/users/admin/service.py` | `UserService(_UserServiceBase)`: write/command methods + new `create_user` / `update_details` / `delete_user`. |
| `modules/users/users/contracts/schemas.py` | + `UserAdminCreate`, `UserDetailsUpdate`. |
| `modules/users/users/contracts/events.py` | + `UserCreated`, `UserDeleted`. |
| `modules/users/users/exceptions.py` | + `EmailAlreadyExistsError`. |
| `modules/users/users/admin/api.py` | + `POST ""`, `PATCH "/{user_id}"`, `DELETE "/{user_id}"`. |
| `modules/users/users/admin/views.py` | + `GET /admin/create` Inertia page route. |
| `modules/users/users/pages/Users/Create.tsx` | NEW — create-user form. |
| `modules/users/users/pages/Users/Index.tsx` | + "Create user" button next to "Invite member". |
| `modules/users/users/pages/Users/Edit.tsx` | + render `DetailsCard` + `DangerZone`. |
| `modules/users/users/pages/Users/components/DetailsCard.tsx` | NEW — edit email + full name. |
| `modules/users/users/pages/Users/components/DangerZone.tsx` | NEW — delete with confirm dialog. |
| `modules/users/tests/test_service_admin.py` | + create/update/delete service tests. |
| `modules/users/tests/test_api_admin.py` | + create/update/delete API tests. |
| `modules/users/tests/test_views_admin.py` | + create-page view test. |

---

## Task 1: Split `admin/service.py` into queries + service (pure refactor)

No behavior change. Move read/helper methods to a new `_UserServiceBase` in `queries.py`; leave write methods on `UserService`, which now subclasses the base. Existing import path and every caller/test stay unchanged.

**Files:**
- Create: `modules/users/users/admin/queries.py`
- Modify: `modules/users/users/admin/service.py` (full rewrite — same behavior)
- Test: existing `modules/users/tests/test_service_admin.py`, `test_api_admin.py`, `test_views_admin.py` (unchanged — they must still pass)

**Interfaces:**
- Produces: `class _UserServiceBase` (in `queries.py`) with `__init__(self, db, user_manager)`, `_resolve_roles`, `to_list_item`, `list_roles`, `_get_user_with_roles`, `_require_user`, `list_users`, `count_user_states`, `get_with_roles`, `get_list_item`. And `class UserService(_UserServiceBase)` (in `service.py`) with `invite`, `disable`, `enable`, `mark_verified`, `set_roles`, `generate_reset_link`.

- [ ] **Step 1: Create `admin/queries.py` with the read/helper base class**

```python
"""Read/query helpers for the admin UserService (split from service.py)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.contracts.schemas import RoleListItem, UserListItem
from users.exceptions import UserNotFoundError
from users.manager import UserManager
from users.models import Role, User, UserRole


class _UserServiceBase:
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

    def to_list_item(self, user: User) -> UserListItem:
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

    async def list_roles(self) -> list[RoleListItem]:
        stmt = (
            select(Role, func.count(UserRole.user_id))
            .outerjoin(UserRole, UserRole.role_id == Role.id)
            .group_by(Role.id)
            .order_by(Role.name)
        )
        result = await self._db.execute(stmt)
        return [
            RoleListItem(
                id=role.id,
                name=role.name,
                description=role.description,
                user_count=user_count,
            )
            for role, user_count in result.all()
        ]

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

    # ── Queries ──────────────────────────────────────────────────

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
        """Returns (items, total_count). last_login_at sort always uses NULLS LAST."""
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

        items = [self.to_list_item(u) for u in rows]
        return items, total

    async def count_user_states(self) -> dict[str, int]:
        """Workspace-wide counts unaffected by list filters/pagination —
        feeds the dashboard cards on /users/admin so they don't reflect
        the current page slice."""
        active_q = select(func.count()).select_from(User).where(User.is_active.is_(True))
        unverified_q = (
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True), User.is_verified.is_(False))
        )
        active = (await self._db.execute(active_q)).scalar_one()
        unverified = (await self._db.execute(unverified_q)).scalar_one()
        return {"active": int(active), "unverified": int(unverified)}

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        return await self._get_user_with_roles(user_id)

    async def get_list_item(self, user_id: uuid.UUID) -> UserListItem:
        user = await self._require_user(user_id)
        return self.to_list_item(user)
```

- [ ] **Step 2: Rewrite `admin/service.py` to subclass the base, keeping only write methods**

```python
"""UserService — admin write operations (reads live in queries.py)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from users.admin.queries import _UserServiceBase
from users.contracts.schemas import UserCreate
from users.models import User, UserRole


class UserService(_UserServiceBase):
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

    async def mark_verified(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        if not user.is_verified:
            user.is_verified = True
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
```

- [ ] **Step 3: Run the existing admin test suites to verify the refactor is behavior-preserving**

Run: `uv run pytest modules/users/tests/test_service_admin.py modules/users/tests/test_api_admin.py modules/users/tests/test_views_admin.py modules/users/tests/test_invite_flow.py -v`
Expected: PASS (all existing tests green — no behavior changed).

- [ ] **Step 4: Verify both files are under the line cap**

Run: `uv run python scripts/check_file_size.py modules/users/users/admin/queries.py modules/users/users/admin/service.py`
Expected: no violations (queries.py ≈ 175 lines, service.py ≈ 130 lines).

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/admin/queries.py modules/users/users/admin/service.py
git commit -m "refactor(users): split admin UserService into queries + service"
```

---

## Task 2: Backend — create user (active + verified)

**Files:**
- Modify: `modules/users/users/contracts/schemas.py` (+ `UserAdminCreate`)
- Modify: `modules/users/users/contracts/events.py` (+ `UserCreated`)
- Modify: `modules/users/users/admin/service.py` (+ `create_user`)
- Modify: `modules/users/users/admin/api.py` (+ `POST ""`)
- Test: `modules/users/tests/test_service_admin.py`, `modules/users/tests/test_api_admin.py`

**Interfaces:**
- Consumes: `_UserServiceBase._resolve_roles`, `.to_list_item`; `UserManager.create`.
- Produces:
  - `class UserAdminCreate(SQLModel)`: `email: EmailStr`, `password: str`, `full_name: str | None = None`, `role_names: list[str] = []`.
  - `class UserCreated(Event)`: `user_id: uuid.UUID`, `email: str`, `created_by: str | None`.
  - `UserService.create_user(self, email: str, password: str, full_name: str | None, role_names: list[str], *, created_by: str | None) -> User`.
  - Endpoint `POST /api/users/admin` → `UserListItem`, 201.

- [ ] **Step 1: Write the failing service test**

Append to `modules/users/tests/test_service_admin.py`:

```python
# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_user_active_verified_with_roles(users_app):
    """create_user makes an active+verified user and assigns roles."""
    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        user = await svc.create_user(
            email="created@example.com",
            password="SecurePass1!",
            full_name="Created User",
            role_names=["user"],
            created_by="admin-id",
        )
        assert user.is_active is True
        assert user.is_verified is True
        assert user.email == "created@example.com"
        assert user.full_name == "Created User"
        assert [r.name for r in user.roles] == ["user"]


@pytest.mark.anyio
async def test_create_user_weak_password_rejected(users_app):
    from fastapi_users import exceptions as fa_exc

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        with pytest.raises(fa_exc.InvalidPasswordException):
            await svc.create_user(
                email="weak@example.com",
                password="short",
                full_name=None,
                role_names=[],
                created_by=None,
            )


@pytest.mark.anyio
async def test_create_user_duplicate_email_rejected(users_app):
    from fastapi_users import exceptions as fa_exc

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        await svc.create_user(
            email="dup@example.com",
            password="SecurePass1!",
            full_name=None,
            role_names=[],
            created_by=None,
        )
        await session.flush()
        with pytest.raises(fa_exc.UserAlreadyExists):
            await svc.create_user(
                email="dup@example.com",
                password="SecurePass1!",
                full_name=None,
                role_names=[],
                created_by=None,
            )
```

- [ ] **Step 2: Run the service test to verify it fails**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k create_user -v`
Expected: FAIL with `AttributeError: 'UserService' object has no attribute 'create_user'`.

- [ ] **Step 3: Add `UserAdminCreate` schema**

In `modules/users/users/contracts/schemas.py`, after the `UserInvite` class (around line 49), add:

```python
class UserAdminCreate(SQLModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_names: list[str] = []
```

- [ ] **Step 4: Add `UserCreated` event**

In `modules/users/users/contracts/events.py`, after the `UserInvited` class, add:

```python
@dataclass
class UserCreated(Event):
    user_id: uuid.UUID
    email: str
    created_by: str | None
```

- [ ] **Step 5: Add `create_user` to `UserService`**

In `modules/users/users/admin/service.py`, the schemas import already pulls in `UserCreate`; add this method to the `UserService` class (place it before `invite`):

```python
    async def create_user(
        self,
        email: str,
        password: str,
        full_name: str | None,
        role_names: list[str],
        *,
        created_by: str | None,
    ) -> User:
        """Create an active+verified user with an admin-set password.

        Reuses ``manager.create`` for the password policy + email-uniqueness
        check. ``is_verified=True`` means ``on_after_register`` does not fire a
        verification email (and with no request, no event is published here —
        the endpoint publishes ``UserCreated``)."""
        user_create = UserCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        user = await self._manager.create(user_create, safe=False)

        roles = await self._resolve_roles(role_names)
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=created_by,
                )
            )
        if roles:
            await self._db.flush()
            await self._db.refresh(user, attribute_names=["roles"])
        return user
```

- [ ] **Step 6: Run the service test to verify it passes**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k create_user -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Write the failing API test**

Append to `modules/users/tests/test_api_admin.py`:

```python
# ---------------------------------------------------------------------------
# Admin create
# ---------------------------------------------------------------------------


class TestAdminCreate:
    @pytest.mark.anyio
    async def test_create_returns_201(self, admin_client):
        resp = await admin_client.post(
            "/api/users/admin",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass1!",
                "full_name": "New User",
                "role_names": ["user"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["is_active"] is True
        assert body["is_verified"] is True
        assert body["roles"] == ["user"]

    @pytest.mark.anyio
    async def test_create_duplicate_returns_409(self, admin_client, users_db):
        await _make_user(users_db, email="taken@example.com")
        resp = await admin_client.post(
            "/api/users/admin",
            json={"email": "taken@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_create_weak_password_returns_400(self, admin_client):
        resp = await admin_client.post(
            "/api/users/admin",
            json={"email": "weakpw@example.com", "password": "short"},
        )
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_create_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.post(
            "/api/users/admin",
            json={"email": "hacker@example.com", "password": "SecurePass1!"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Not authenticated"}
```

- [ ] **Step 8: Run the API test to verify it fails**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminCreate -v`
Expected: FAIL — `POST /api/users/admin` returns 405 (Method Not Allowed) because the endpoint doesn't exist yet.

- [ ] **Step 9: Add the `POST ""` endpoint**

In `modules/users/users/admin/api.py`:

Add the fastapi-users exceptions import (after `from fastapi import status as http_status`):

```python
from fastapi_users import exceptions as fa_exceptions
```

Change the events import to include `UserCreated`:

```python
from users.contracts.events import RoleAssigned, UserCreated, UserDisabled, UserInvited
```

Change the schemas import to include `UserAdminCreate`:

```python
from users.contracts.schemas import (
    PasswordResetLink,
    RoleAssignment,
    UserAdminCreate,
    UserInvite,
    UserListItem,
)
```

Then add the endpoint immediately after `admin_invite_user` (before `admin_disable_user`):

```python
@admin_router.post(
    "",
    response_model=UserListItem,
    status_code=http_status.HTTP_201_CREATED,
)
async def admin_create_user(
    data: UserAdminCreate,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Create an active+verified user with an admin-set password."""
    creator = getattr(request.state, "user", None)
    created_by = creator.id if creator else None
    try:
        user = await service.create_user(
            data.email,
            data.password,
            data.full_name,
            data.role_names,
            created_by=created_by,
        )
    except fa_exceptions.UserAlreadyExists:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists.",
        ) from None
    except fa_exceptions.InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=exc.reason) from None
    await bus.publish(
        UserCreated(user_id=user.id, email=user.email, created_by=created_by)
    )
    return service.to_list_item(user)
```

- [ ] **Step 10: Run the API test to verify it passes**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminCreate -v`
Expected: PASS (4 tests).

- [ ] **Step 11: Commit**

```bash
git add modules/users/users/contracts/schemas.py modules/users/users/contracts/events.py \
        modules/users/users/admin/service.py modules/users/users/admin/api.py \
        modules/users/tests/test_service_admin.py modules/users/tests/test_api_admin.py
git commit -m "feat(users): admin create-user endpoint (active+verified)"
```

---

## Task 3: Backend — edit user details (email + full name)

**Files:**
- Modify: `modules/users/users/contracts/schemas.py` (+ `UserDetailsUpdate`)
- Modify: `modules/users/users/exceptions.py` (+ `EmailAlreadyExistsError`)
- Modify: `modules/users/users/admin/service.py` (+ `update_details`)
- Modify: `modules/users/users/admin/api.py` (+ `PATCH "/{user_id}"`)
- Test: `modules/users/tests/test_service_admin.py`, `modules/users/tests/test_api_admin.py`

**Interfaces:**
- Consumes: `_UserServiceBase._require_user`, `.to_list_item`.
- Produces:
  - `class UserDetailsUpdate(SQLModel)`: `email: EmailStr`, `full_name: str | None = None`.
  - `class EmailAlreadyExistsError(Exception)`: `__init__(self, email: str)`, attribute `.email`.
  - `UserService.update_details(self, user_id: uuid.UUID, email: str, full_name: str | None) -> User`.
  - Endpoint `PATCH /api/users/admin/{user_id}` → `UserListItem`, 200.

- [ ] **Step 1: Write the failing service test**

Append to `modules/users/tests/test_service_admin.py`:

```python
# ---------------------------------------------------------------------------
# update_details
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_details_changes_email_and_name(users_app):
    from test_api_admin import _make_user

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="old@example.com")
        svc = _build_service(session, users_app)
        updated = await svc.update_details(
            user.id, email="new@example.com", full_name="New Name"
        )
        assert updated.email == "new@example.com"
        assert updated.full_name == "New Name"


@pytest.mark.anyio
async def test_update_details_duplicate_email_rejected(users_app):
    from test_api_admin import _make_user
    from users.exceptions import EmailAlreadyExistsError

    async with users_app.state.sm.db.session_factory() as session:
        await _make_user(session, email="a@example.com")
        target = await _make_user(session, email="b@example.com")
        svc = _build_service(session, users_app)
        with pytest.raises(EmailAlreadyExistsError):
            await svc.update_details(target.id, email="a@example.com", full_name=None)


@pytest.mark.anyio
async def test_update_details_same_email_is_allowed(users_app):
    from test_api_admin import _make_user

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="keep@example.com")
        svc = _build_service(session, users_app)
        updated = await svc.update_details(
            user.id, email="keep@example.com", full_name="Renamed"
        )
        assert updated.email == "keep@example.com"
        assert updated.full_name == "Renamed"
```

- [ ] **Step 2: Run the service test to verify it fails**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k update_details -v`
Expected: FAIL with `AttributeError: 'UserService' object has no attribute 'update_details'`.

- [ ] **Step 3: Add `EmailAlreadyExistsError`**

In `modules/users/users/exceptions.py`, after `UserNotFoundError`, add:

```python
class EmailAlreadyExistsError(Exception):
    """Raised when updating a user to an email already owned by another user."""

    def __init__(self, email: str) -> None:
        super().__init__(f"Email {email} already in use")
        self.email = email
```

- [ ] **Step 4: Add `UserDetailsUpdate` schema**

In `modules/users/users/contracts/schemas.py`, after `UserAdminCreate`, add:

```python
class UserDetailsUpdate(SQLModel):
    email: EmailStr
    full_name: str | None = None
```

- [ ] **Step 5: Add `update_details` to `UserService`**

In `modules/users/users/admin/service.py`:

Change the sqlalchemy import (currently `from sqlalchemy import delete`) to add `func` and `select`:

```python
from sqlalchemy import delete, func, select
```

Add the `EmailAlreadyExistsError` import (this file currently imports nothing from `users.exceptions`):

```python
from users.exceptions import EmailAlreadyExistsError
```

Add the method to `UserService` (place after `create_user`):

```python
    async def update_details(
        self,
        user_id: uuid.UUID,
        email: str,
        full_name: str | None,
    ) -> User:
        """Update a user's email + full name. Raises UserNotFoundError if the
        user is missing, EmailAlreadyExistsError if the new email is taken by
        another user."""
        user = await self._require_user(user_id)
        if email.lower() != user.email.lower():
            clash = await self._db.execute(
                select(User.id).where(
                    func.lower(User.email) == email.lower(),
                    User.id != user_id,
                )
            )
            if clash.scalar_one_or_none() is not None:
                raise EmailAlreadyExistsError(email)
        user.email = email
        user.full_name = full_name
        await self._db.flush()
        return user
```

- [ ] **Step 6: Run the service test to verify it passes**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k update_details -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Write the failing API test**

Append to `modules/users/tests/test_api_admin.py`:

```python
# ---------------------------------------------------------------------------
# Admin update details
# ---------------------------------------------------------------------------


class TestAdminUpdate:
    @pytest.mark.anyio
    async def test_update_changes_email_and_name(self, admin_client, users_db):
        user = await _make_user(users_db, email="before@example.com")
        resp = await admin_client.patch(
            f"/api/users/admin/{user.id}",
            json={"email": "after@example.com", "full_name": "After Name"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "after@example.com"
        assert body["full_name"] == "After Name"

    @pytest.mark.anyio
    async def test_update_duplicate_email_returns_409(self, admin_client, users_db):
        await _make_user(users_db, email="exists@example.com")
        target = await _make_user(users_db, email="target@example.com")
        resp = await admin_client.patch(
            f"/api/users/admin/{target.id}",
            json={"email": "exists@example.com"},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_update_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.patch(
            f"/api/users/admin/{uuid.uuid4()}",
            json={"email": "ghost@example.com"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_update_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.patch(
            f"/api/users/admin/{uuid.uuid4()}",
            json={"email": "x@example.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
```

- [ ] **Step 8: Run the API test to verify it fails**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminUpdate -v`
Expected: FAIL — `PATCH /api/users/admin/{id}` returns 405 (endpoint doesn't exist).

- [ ] **Step 9: Add the `PATCH "/{user_id}"` endpoint**

In `modules/users/users/admin/api.py`:

Add `EmailAlreadyExistsError` to the exceptions import:

```python
from users.exceptions import EmailAlreadyExistsError, UserNotFoundError
```

Add `UserDetailsUpdate` to the schemas import block:

```python
from users.contracts.schemas import (
    PasswordResetLink,
    RoleAssignment,
    UserAdminCreate,
    UserDetailsUpdate,
    UserInvite,
    UserListItem,
)
```

Add the endpoint after `admin_create_user` (before `admin_disable_user`):

```python
@admin_router.patch("/{user_id}", response_model=UserListItem)
async def admin_update_user(
    user_id: uuid.UUID,
    data: UserDetailsUpdate,
    service: UserService = Depends(get_user_service),
):
    """Update a user's email and full name."""
    try:
        user = await service.update_details(user_id, data.email, data.full_name)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="A user with this email already exists.",
        ) from None
    return service.to_list_item(user)
```

- [ ] **Step 10: Run the API test to verify it passes**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminUpdate -v`
Expected: PASS (4 tests).

- [ ] **Step 11: Commit**

```bash
git add modules/users/users/contracts/schemas.py modules/users/users/exceptions.py \
        modules/users/users/admin/service.py modules/users/users/admin/api.py \
        modules/users/tests/test_service_admin.py modules/users/tests/test_api_admin.py
git commit -m "feat(users): admin edit-user-details endpoint"
```

---

## Task 4: Backend — delete user (hard delete, self-delete guarded)

**Files:**
- Modify: `modules/users/users/contracts/events.py` (+ `UserDeleted`)
- Modify: `modules/users/users/admin/service.py` (+ `delete_user`)
- Modify: `modules/users/users/admin/api.py` (+ `DELETE "/{user_id}"`)
- Test: `modules/users/tests/test_service_admin.py`, `modules/users/tests/test_api_admin.py`

**Interfaces:**
- Consumes: `_UserServiceBase._require_user`.
- Produces:
  - `class UserDeleted(Event)`: `user_id: uuid.UUID`.
  - `UserService.delete_user(self, user_id: uuid.UUID) -> None`.
  - Endpoint `DELETE /api/users/admin/{user_id}` → 204; 400 on self-delete; 404 missing.

- [ ] **Step 1: Write the failing service test**

Append to `modules/users/tests/test_service_admin.py`:

```python
# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_user_removes_user_and_roles(users_app):
    from sqlalchemy import select
    from test_api_admin import _make_user
    from users.models import User, UserRole

    async with users_app.state.sm.db.session_factory() as session:
        user = await _make_user(session, email="todelete@example.com", role_names=["admin"])
        svc = _build_service(session, users_app)
        await svc.delete_user(user.id)
        await session.flush()

        remaining = (
            await session.execute(select(User).where(User.id == user.id))
        ).scalar_one_or_none()
        assert remaining is None
        roles = (
            (await session.execute(select(UserRole).where(UserRole.user_id == user.id)))
            .scalars()
            .all()
        )
        assert roles == []


@pytest.mark.anyio
async def test_delete_user_nonexistent_raises(users_app):
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        svc = _build_service(session, users_app)
        with pytest.raises(UserNotFoundError):
            await svc.delete_user(uuid.uuid4())
```

- [ ] **Step 2: Run the service test to verify it fails**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k delete_user -v`
Expected: FAIL with `AttributeError: 'UserService' object has no attribute 'delete_user'`.

- [ ] **Step 3: Add `UserDeleted` event**

In `modules/users/users/contracts/events.py`, after `UserCreated`, add:

```python
@dataclass
class UserDeleted(Event):
    user_id: uuid.UUID
```

- [ ] **Step 4: Add `delete_user` to `UserService`**

In `modules/users/users/admin/service.py`:

Extend the models import to cover every child table:

```python
from users.models import OAuthAccount, RefreshToken, User, UserAccessToken, UserRole
```

Add the method to `UserService` (place after `update_details`):

```python
    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Hard-delete a user and its dependent rows.

        Child rows are deleted explicitly (not via FK cascade) so the result is
        identical on Postgres and SQLite — SQLite only enforces FK cascade when
        the per-connection ``foreign_keys`` pragma is on, which we don't rely
        on. RefreshToken has no DB cascade at all, so it must be cleared here."""
        user = await self._require_user(user_id)
        for model in (UserRole, UserAccessToken, OAuthAccount, RefreshToken):
            await self._db.execute(delete(model).where(model.user_id == user_id))
        await self._db.delete(user)
        await self._db.flush()
```

- [ ] **Step 5: Run the service test to verify it passes**

Run: `uv run pytest modules/users/tests/test_service_admin.py -k delete_user -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Write the failing API test**

Append to `modules/users/tests/test_api_admin.py`:

```python
# ---------------------------------------------------------------------------
# Admin delete
# ---------------------------------------------------------------------------


class TestAdminDelete:
    @pytest.mark.anyio
    async def test_delete_returns_204(self, admin_client, users_db):
        user = await _make_user(users_db, email="deleteme@example.com")
        resp = await admin_client.delete(f"/api/users/admin/{user.id}")
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_delete_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.delete(f"/api/users/admin/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_delete_self_returns_400(self, admin_client, users_app):
        from sqlalchemy import select

        async with users_app.state.sm.db.session_factory() as session:
            admin = (
                await session.execute(
                    select(User).where(User.email == "admin@example.com")
                )
            ).scalar_one()
        resp = await admin_client.delete(f"/api/users/admin/{admin.id}")
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_delete_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.delete(
            f"/api/users/admin/{uuid.uuid4()}",
            follow_redirects=False,
        )
        assert resp.status_code == 401
```

- [ ] **Step 7: Run the API test to verify it fails**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminDelete -v`
Expected: FAIL — `DELETE /api/users/admin/{id}` returns 405 (endpoint doesn't exist).

- [ ] **Step 8: Add the `DELETE "/{user_id}"` endpoint**

In `modules/users/users/admin/api.py`:

Add `Response` to the fastapi import:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response
```

Add `UserDeleted` to the events import:

```python
from users.contracts.events import (
    RoleAssigned,
    UserCreated,
    UserDeleted,
    UserDisabled,
    UserInvited,
)
```

Add the endpoint after `admin_update_user` (before `admin_disable_user`):

```python
@admin_router.delete("/{user_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: uuid.UUID,
    request: Request,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Hard-delete a user. An admin cannot delete their own account."""
    actor = getattr(request.state, "user", None)
    if actor is not None and str(user_id) == actor.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account.",
        )
    try:
        await service.delete_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    await bus.publish(UserDeleted(user_id=user_id))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 9: Run the API test to verify it passes**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminDelete -v`
Expected: PASS (4 tests).

- [ ] **Step 10: Run the whole admin API + service suite to confirm no route collisions**

Run: `uv run pytest modules/users/tests/test_api_admin.py modules/users/tests/test_service_admin.py modules/users/tests/test_api_admin_filters.py -v`
Expected: PASS (existing + new tests; `PATCH/DELETE /{user_id}` do not shadow `/{user_id}/disable` etc.).

- [ ] **Step 11: Commit**

```bash
git add modules/users/users/contracts/events.py modules/users/users/admin/service.py \
        modules/users/users/admin/api.py \
        modules/users/tests/test_service_admin.py modules/users/tests/test_api_admin.py
git commit -m "feat(users): admin delete-user endpoint (hard delete, self-delete guarded)"
```

---

## Task 5: View route — `GET /admin/create`

**Files:**
- Modify: `modules/users/users/admin/views.py` (+ create-page route + page constant)
- Test: `modules/users/tests/test_views_admin.py`

**Interfaces:**
- Consumes: `_roles_payload(app)` (existing helper).
- Produces: view route `GET /users/admin/create` rendering Inertia component `Users/Users/Create` with prop `roles`.

- [ ] **Step 1: Write the failing view test**

Append to `modules/users/tests/test_views_admin.py`:

```python
# ---------------------------------------------------------------------------
# Admin create page
# ---------------------------------------------------------------------------


class TestAdminCreatePage:
    @pytest.mark.anyio
    async def test_create_page_renders_with_roles(self, admin_client):
        resp = await admin_client.get(
            "/users/admin/create",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["component"] == "Users/Users/Create"
        assert "roles" in data["props"]

    @pytest.mark.anyio
    async def test_create_page_requires_auth(self, anon_client):
        resp = await anon_client.get("/users/admin/create", follow_redirects=False)
        assert resp.status_code == 302
```

- [ ] **Step 2: Run the view test to verify it fails**

Run: `uv run pytest modules/users/tests/test_views_admin.py::TestAdminCreatePage -v`
Expected: FAIL — `test_create_page_renders_with_roles` hits the edit route (the `/admin/{user_id}` route catches `create` as a user_id and 404s). Confirms route ordering matters.

- [ ] **Step 3: Add the create-page route (before the `/admin/{user_id}` route)**

In `modules/users/users/admin/views.py`:

Add the page constant after `_PAGE_ADMIN_INVITE`:

```python
_PAGE_ADMIN_CREATE = "Users/Users/Create"
```

Insert this route between `admin_invite_page` and `admin_edit_page` (it MUST come before `admin_edit_page`, which owns `/admin/{user_id}`):

```python
@router.get(
    "/admin/create",
    response_model=None,
    dependencies=[Depends(RequiresPermission(PERM_USERS_MANAGE))],
)
async def admin_create_page(
    request: Request,
    inertia: InertiaDep,
) -> InertiaResponse:
    return await inertia.render(
        _PAGE_ADMIN_CREATE,
        {
            "roles": await _roles_payload(request.app),
        },
    )
```

- [ ] **Step 4: Run the view test to verify it passes**

Run: `uv run pytest modules/users/tests/test_views_admin.py::TestAdminCreatePage -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/admin/views.py modules/users/tests/test_views_admin.py
git commit -m "feat(users): admin create-user view route"
```

---

## Task 6: Frontend — Create page + "Create user" button

**Files:**
- Create: `modules/users/users/pages/Users/Create.tsx`
- Modify: `modules/users/users/pages/Users/Index.tsx` (actions: add "Create user")

**Interfaces:**
- Consumes: view route `GET /users/admin/create` (props `roles`), endpoint `POST /api/users/admin`.

- [ ] **Step 1: Create `Create.tsx`**

Create `modules/users/users/pages/Users/Create.tsx`:

```tsx
import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Lock, Mail, UserPlus } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface Role {
  id: string;
  name: string;
}

interface Props {
  roles: Role[];
}

function Create() {
  const { roles } = usePage<{ props: Props }>().props as unknown as Props;

  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    fetch('/api/users/admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        password,
        full_name: fullName || null,
        role_names: selectedRoles,
      }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('User created');
          router.visit('/users/admin');
        } else {
          const data = await res.json().catch(() => ({}));
          setError(typeof data?.detail === 'string' ? data.detail : 'Failed to create user');
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  return (
    <PageShell
      title="Create user"
      description="The account is active and verified immediately — share the password securely."
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">Back to Users</Link>
        </Button>
      }
    >
      <Card className="max-w-xl border-border">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
                Email <span className="text-destructive">*</span>
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="teammate@example.com"
                  required
                  autoComplete="off"
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="full_name" className="text-sm font-medium text-muted-foreground">
                Full name (optional)
              </Label>
              <Input
                id="full_name"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Doe"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
                Password <span className="text-destructive">*</span>
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  required
                  autoComplete="new-password"
                  className="pl-9"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Must be at least 8 characters and not all numbers.
              </p>
            </div>

            {roles.length > 0 && (
              <div className="space-y-2">
                <Label className="text-sm font-medium text-muted-foreground">Role</Label>
                <div className="flex flex-wrap gap-1.5">
                  {roles.map((role) => {
                    const active = selectedRoles.includes(role.name);
                    return (
                      <button
                        key={role.id}
                        type="button"
                        onClick={() => toggleRole(role.name)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                          active
                            ? 'border-primary-200 bg-primary-600/10 text-primary-700'
                            : 'border-border bg-card text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {role.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button asChild variant="outline">
                <Link href="/users/admin">Cancel</Link>
              </Button>
              <Button type="submit" disabled={loading} className="gap-1.5">
                <UserPlus className="h-3.5 w-3.5" />
                {loading ? 'Creating…' : 'Create user'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Create.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Create;
```

- [ ] **Step 2: Add the "Create user" button to `Index.tsx`**

In `modules/users/users/pages/Users/Index.tsx`, replace the `actions` prop of `PageShell` (currently a single Button linking to `/users/admin/invite`) with two buttons:

```tsx
      actions={
        <div className="flex gap-2">
          <Button asChild className="gap-1.5">
            <Link href="/users/admin/create">
              <Plus className="h-4 w-4" />
              Create user
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-1.5">
            <Link href="/users/admin/invite">
              <Mail className="h-4 w-4" />
              Invite member
            </Link>
          </Button>
        </div>
      }
```

(`Plus` and `Mail` are already imported in `Index.tsx`.)

- [ ] **Step 3: Regenerate module page manifests so Vite/tsc pick up the new page**

Run: `make gen-pages`
Expected: `host/client_app/modules.generated.ts` now references `Users/Create`.

- [ ] **Step 4: Typecheck + lint the frontend changes**

Run: `npx biome check modules/users/users/pages/Users/Create.tsx modules/users/users/pages/Users/Index.tsx`
Expected: no errors. Then run the per-workspace TS check (`make lint` runs the full sweep) — Expected: no `tsc` errors.

- [ ] **Step 5: Verify both files are under the line cap**

Run: `uv run python scripts/check_file_size.py modules/users/users/pages/Users/Create.tsx modules/users/users/pages/Users/Index.tsx`
Expected: no violations (Create.tsx ≈ 200 lines, Index.tsx ≈ 275 lines).

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/pages/Users/Create.tsx modules/users/users/pages/Users/Index.tsx \
        host/client_app/modules.generated.ts host/client_app/modules.manifest.json \
        host/client_app/modules.generated.css
git commit -m "feat(users): create-user page + Create button on admin index"
```

---

## Task 7: Frontend — DetailsCard + DangerZone wired into Edit

**Files:**
- Create: `modules/users/users/pages/Users/components/DetailsCard.tsx`
- Create: `modules/users/users/pages/Users/components/DangerZone.tsx`
- Modify: `modules/users/users/pages/Users/Edit.tsx` (render both; pass current-user id)

**Interfaces:**
- Consumes: endpoints `PATCH /api/users/admin/{id}`, `DELETE /api/users/admin/{id}`; Inertia shared prop `auth.user.id` (string).
- Produces:
  - `DetailsCard({ user }: { user: { id: string; email: string; full_name: string | null } })`.
  - `DangerZone({ userId, email, isSelf }: { userId: string; email: string; isSelf: boolean })`.

- [ ] **Step 1: Create `components/DetailsCard.tsx`**

Create `modules/users/users/pages/Users/components/DetailsCard.tsx`:

```tsx
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  user: { id: string; email: string; full_name: string | null };
}

export function DetailsCard({ user }: Props) {
  const [email, setEmail] = useState(user.email);
  const [fullName, setFullName] = useState(user.full_name ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    setSaving(true);
    setError(null);
    fetch(`/api/users/admin/${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, full_name: fullName || null }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Details updated');
        } else {
          const data = await res.json().catch(() => ({}));
          setError(typeof data?.detail === 'string' ? data.detail : 'Failed to update details');
        }
      })
      .catch(() => setError('An error occurred'))
      .finally(() => setSaving(false));
  };

  return (
    <Card className="border-border lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle
          right={
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save details'}
            </Button>
          }
        >
          Details
        </SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="edit-email" className="text-sm font-medium text-muted-foreground">
              Email
            </Label>
            <Input
              id="edit-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="edit-full-name" className="text-sm font-medium text-muted-foreground">
              Full name
            </Label>
            <Input
              id="edit-full-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
            />
          </div>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Create `components/DangerZone.tsx`**

Create `modules/users/users/pages/Users/components/DangerZone.tsx`:

```tsx
import { router } from '@inertiajs/react';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  userId: string;
  email: string;
  isSelf: boolean;
}

export function DangerZone({ userId, email, isSelf }: Props) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = () => {
    setDeleting(true);
    fetch(`/api/users/admin/${userId}`, { method: 'DELETE' })
      .then(async (res) => {
        if (res.ok) {
          toast.success('User deleted');
          router.visit('/users/admin');
        } else {
          const data = await res.json().catch(() => ({}));
          toast.error(typeof data?.detail === 'string' ? data.detail : 'Failed to delete user');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setDeleting(false));
  };

  return (
    <Card className="border-destructive/40 lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle>Danger zone</SectionTitle>
        {isSelf ? (
          <p className="text-sm text-muted-foreground">You cannot delete your own account.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">
              Permanently delete this user. This cannot be undone.
            </p>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="gap-1.5" disabled={deleting}>
                  <Trash2 className="h-3.5 w-3.5" />
                  {deleting ? 'Deleting…' : 'Delete user'}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete {email}?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently removes the account and all of its access. This action cannot
                    be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Wire `DetailsCard` + `DangerZone` into `Edit.tsx`**

In `modules/users/users/pages/Users/Edit.tsx`:

Add the two component imports next to the existing `AccountStatusCard` import:

```tsx
import { AccountStatusCard } from './components/AccountStatusCard';
import { DangerZone } from './components/DangerZone';
import { DetailsCard } from './components/DetailsCard';
```

Extend the `Props` interface to read the current user from the shared `auth` prop:

```tsx
interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
  auth?: { user?: { id?: string } };
}
```

Change the `usePage` destructure and compute `isSelf`:

```tsx
  const { user, roles, has_permissions_module, auth } = usePage<{ props: Props }>()
    .props as unknown as Props;
  const isSelf = auth?.user?.id === user.id;
```

Render `DetailsCard` as the first child inside `<div className="grid gap-4 lg:grid-cols-2">` (immediately before the Metadata `<Card>`):

```tsx
      <div className="grid gap-4 lg:grid-cols-2">
        <DetailsCard user={{ id: user.id, email: user.email, full_name: user.full_name }} />

        <Card className="border-border">
          {/* ...existing Metadata card unchanged... */}
```

Render `DangerZone` as the last child inside that grid, immediately before its closing `</div>` (after the Roles `</Card>`):

```tsx
        <DangerZone userId={user.id} email={user.email} isSelf={isSelf} />
      </div>
```

- [ ] **Step 4: Typecheck + lint the frontend changes**

Run: `npx biome check modules/users/users/pages/Users/components/DetailsCard.tsx modules/users/users/pages/Users/components/DangerZone.tsx modules/users/users/pages/Users/Edit.tsx`
Expected: no errors. Then run `make lint` (full sweep) — Expected: no `tsc` errors.

- [ ] **Step 5: Verify all three files are under the line cap**

Run: `uv run python scripts/check_file_size.py modules/users/users/pages/Users/components/DetailsCard.tsx modules/users/users/pages/Users/components/DangerZone.tsx modules/users/users/pages/Users/Edit.tsx`
Expected: no violations (DetailsCard ≈ 95, DangerZone ≈ 90, Edit.tsx ≈ 245).

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/pages/Users/components/DetailsCard.tsx \
        modules/users/users/pages/Users/components/DangerZone.tsx \
        modules/users/users/pages/Users/Edit.tsx
git commit -m "feat(users): edit-details + delete UI on admin Edit page"
```

---

## Task 8: Full verification gate

**Files:** none changed — this is the final cross-cutting check.

- [ ] **Step 1: Run the full Python test suite**

Run: `make test-py`
Expected: PASS (all users tests + framework tests green).

- [ ] **Step 2: Run the full lint sweep (Ruff/ty/Biome/tsc + 300-line cap)**

Run: `make lint`
Expected: PASS — no formatting, type, or file-size violations across the new/changed files.

- [ ] **Step 3: Run module diagnostics**

Run: `make doctor`
Expected: no NEW `SM0xx` warnings. In particular, confirm no new `SM003` (orphan page) for `Users/Create` — it is rendered by the `admin_create_page` view route — and no `SM018` (the new pages use `fetch`, not Inertia `router.post` to `/api/*`).

- [ ] **Step 4: Manual smoke (optional, requires `make dev`)**

With `make dev` running and logged in as an admin:
1. `/users/admin` → "Create user" → fill email/password → submit → new user appears in list.
2. Log out, log in as the new user → confirms active+verified (login succeeds, no verification wall).
3. Open a user's Edit page → change email + name → Save details → toast, value persists on reload.
4. Edit page → Danger zone → Delete user → confirm → user gone from list.
5. Open your own admin account's Edit page → Danger zone shows "You cannot delete your own account."

---

## Self-Review (completed by plan author)

- **Spec coverage:** create (Task 2), edit details (Task 3), delete + self-delete guard (Task 4), view route (Task 5), Create page + Index button (Task 6), DetailsCard + DangerZone + Edit wiring (Task 7), full verification (Task 8). Service split that the spec calls out (Task 1). New schemas `UserAdminCreate`/`UserDetailsUpdate`, events `UserCreated`/`UserDeleted`, exception `EmailAlreadyExistsError` — all present. Out-of-scope items (direct password-set on existing user, last-admin lockout, verification-on-email-change) intentionally not implemented.
- **Type consistency:** `create_user(email, password, full_name, role_names, *, created_by)`, `update_details(user_id, email, full_name)`, `delete_user(user_id)` are referenced identically in service, API, and tests. `EmailAlreadyExistsError(email)` raised in service, caught in API. `DangerZone` props `{userId, email, isSelf}` and `DetailsCard` props `{user:{id,email,full_name}}` match their Edit.tsx call sites. `request.state.user.id` is a string, so the self-delete guard compares `str(user_id) == actor.id`.
- **No placeholders:** every code step contains complete code; every run step has an exact command and expected result.
