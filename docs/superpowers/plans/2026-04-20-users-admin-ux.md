# Users Admin UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add list filtering + sorting, confirmation dialogs for destructive actions, and an expanded detail page to the Users admin UX.

**Architecture:** Additive changes only — existing endpoints keep their shapes. Filter/sort logic extends `UserService.list_users`; new `PATCH /admin/{id}/verify` endpoint follows the same `UserNotFoundError → 404` pattern as peers. Frontend keeps URL-as-state pattern and adds shadcn AlertDialog wrappers. Permissions module cross-link is rendered only when the module is installed (checked via `app.state.sm.modules`).

**Tech Stack:** Python 3.12 + FastAPI + SQLModel + SQLAlchemy, Inertia.js + React + shadcn (AlertDialog, Select), pytest (asyncio_mode=auto), vitest.

---

## File Structure

**Backend — modify:**
- `modules/users/users/contracts/schemas.py` — `UserListItem` gains `created_at`
- `modules/users/users/service.py` — `list_users` grows filter/sort kwargs; new `mark_verified` method
- `modules/users/users/endpoints/api_admin.py` — new query params on list; new `PATCH /{id}/verify` endpoint
- `modules/users/users/endpoints/views.py` — `admin_index` accepts + echoes filter/sort params; `admin_edit_page` passes `has_permissions_module` flag

**Backend — tests:**
- `modules/users/tests/test_service.py` — filter/sort unit tests, `mark_verified` tests
- `modules/users/tests/test_api_admin.py` — endpoint filter tests + verify endpoint tests
- `modules/users/tests/test_views.py` — view filter tests + detail page cross-link test

**Frontend — modify:**
- `modules/users/users/pages/Users/Index.tsx` — filter controls, sortable headers, Created column
- `modules/users/users/pages/Users/Edit.tsx` — Metadata card, Mark-verified button, AlertDialog for Disable + reset-link, Permissions cross-link

---

## Task 1: `UserListItem` + service return `created_at`

**Files:**
- Modify: `modules/users/users/contracts/schemas.py`
- Modify: `modules/users/users/service.py:37-48` (`to_list_item`)
- Test: `modules/users/tests/test_service.py`

The `User` model already has `created_at` from `AuditMixin`. We add it to the `UserListItem` DTO and surface it in `to_list_item`.

- [ ] **Step 1.1: Write a failing test that `UserListItem` from service includes `created_at`**

Append to `modules/users/tests/test_service.py`:

```python
async def test_to_list_item_includes_created_at(users_db):
    """`UserListItem` carries `created_at` sourced from AuditMixin."""
    from users.manager import UserManager
    from users.service import UserService

    # Create a user directly
    import uuid as _uuid
    from fastapi_users.password import PasswordHelper
    from users.models import User

    user = User(
        id=_uuid.uuid4(),
        email="ts@example.com",
        hashed_password=PasswordHelper().hash("x"),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    users_db.add(user)
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))  # manager unused here
    item = await svc.get_list_item(user.id)
    assert item.created_at is not None
```

- [ ] **Step 1.2: Run it — must fail** (`AttributeError: 'UserListItem' object has no attribute 'created_at'`)

Run: `cd /Volumes/ext1/Sandbox/simple_module_python/goofy-ride-57cdce && uv run pytest modules/users/tests/test_service.py::test_to_list_item_includes_created_at -v`

Expected: FAIL with AttributeError on `item.created_at`.

- [ ] **Step 1.3: Add `created_at` to `UserListItem`**

Edit `modules/users/users/contracts/schemas.py` — `UserListItem` class:

```python
class UserListItem(SQLModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    is_verified: bool
    disabled_at: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    roles: list[str] = []
```

- [ ] **Step 1.4: Surface `created_at` in `to_list_item`**

Edit `modules/users/users/service.py` — `to_list_item`:

```python
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
```

- [ ] **Step 1.5: Run test — must pass**

Run: `uv run pytest modules/users/tests/test_service.py::test_to_list_item_includes_created_at -v`

Expected: PASS.

- [ ] **Step 1.6: Run the whole users test suite — must all pass**

Run: `uv run pytest modules/users/tests/ -q`

Expected: all pass (adding an optional field to the DTO is backward compatible).

- [ ] **Step 1.7: Commit**

```bash
git add modules/users/users/contracts/schemas.py modules/users/users/service.py modules/users/tests/test_service.py
git commit -m "feat(users): expose created_at on UserListItem"
```

---

## Task 2: Service-level filter + sort

**Files:**
- Modify: `modules/users/users/service.py:65-91` (`list_users`)
- Test: `modules/users/tests/test_service.py`

Extend `list_users` signature with keyword args. Filters translate to SQL `WHERE`; sort to SQL `ORDER BY`. Unknown sort/status/verified values raise `ValueError` — the endpoint layer coerces invalid values to defaults before calling.

- [ ] **Step 2.1: Write failing filter test — status**

Append to `test_service.py`:

```python
async def test_list_users_status_disabled_filter(users_db):
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    from datetime import UTC, datetime
    from fastapi_users.password import PasswordHelper
    from users.models import User

    pw = PasswordHelper()
    users_db.add(User(
        id=_uuid.uuid4(), email="active@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True,
    ))
    users_db.add(User(
        id=_uuid.uuid4(), email="off@x.com", hashed_password=pw.hash("x"),
        is_active=False, is_superuser=False, is_verified=True,
        disabled_at=datetime.now(UTC),
    ))
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))
    items, total = await svc.list_users(status="disabled")
    emails = {i.email for i in items}
    assert "off@x.com" in emails
    assert "active@x.com" not in emails
```

- [ ] **Step 2.2: Run — must fail** (`unexpected keyword argument 'status'`)

Run: `uv run pytest modules/users/tests/test_service.py::test_list_users_status_disabled_filter -v`

Expected: FAIL with TypeError.

- [ ] **Step 2.3: Write failing filter tests — role, verified, sort**

Append to `test_service.py`:

```python
async def test_list_users_role_filter(users_db):
    """role_name filter returns only users with that role."""
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    from fastapi_users.password import PasswordHelper
    from sqlalchemy import select
    from users.models import Role, User, UserRole

    pw = PasswordHelper()
    admin_role = (await users_db.execute(select(Role).where(Role.name == "admin"))).scalar_one()

    admin_user = User(
        id=_uuid.uuid4(), email="role-a@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True,
    )
    plain_user = User(
        id=_uuid.uuid4(), email="role-b@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True,
    )
    users_db.add(admin_user)
    users_db.add(plain_user)
    await users_db.flush()
    users_db.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))
    items, _ = await svc.list_users(role_name="admin")
    emails = {i.email for i in items}
    assert "role-a@x.com" in emails
    assert "role-b@x.com" not in emails


async def test_list_users_verified_filter(users_db):
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    from fastapi_users.password import PasswordHelper
    from users.models import User

    pw = PasswordHelper()
    users_db.add(User(id=_uuid.uuid4(), email="v@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True))
    users_db.add(User(id=_uuid.uuid4(), email="u@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=False))
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))
    items, _ = await svc.list_users(verified="no")
    emails = {i.email for i in items}
    assert "u@x.com" in emails
    assert "v@x.com" not in emails


async def test_list_users_sort_last_login_desc_nulls_last(users_db):
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta
    from fastapi_users.password import PasswordHelper
    from users.models import User

    pw = PasswordHelper()
    now = datetime.now(UTC)
    users_db.add(User(id=_uuid.uuid4(), email="recent@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True, last_login_at=now))
    users_db.add(User(id=_uuid.uuid4(), email="old@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True,
        last_login_at=now - timedelta(days=7)))
    users_db.add(User(id=_uuid.uuid4(), email="never@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=True))
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))
    items, _ = await svc.list_users(sort="last_login_at", order="desc")
    emails = [i.email for i in items if i.email.endswith("@x.com")]
    # recent → old → never (NULLs last regardless of desc)
    assert emails.index("recent@x.com") < emails.index("old@x.com")
    assert emails.index("old@x.com") < emails.index("never@x.com")
```

- [ ] **Step 2.4: Run all four — must fail**

Run: `uv run pytest modules/users/tests/test_service.py -k "list_users_status or list_users_role or list_users_verified or list_users_sort" -v`

Expected: all FAIL with TypeError on unknown kwargs.

- [ ] **Step 2.5: Extend `list_users` with filter + sort kwargs**

Replace `modules/users/users/service.py:65-91` with:

```python
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

        Filters:
          - search: email/full_name ILIKE pattern
          - status: "active" | "disabled" | None (=all)
          - role_name: users holding this role
          - verified: "yes" | "no" | None (=all)
        Sort columns: "email" | "last_login_at" | "created_at"
        Order: "asc" | "desc". last_login_at sorts NULLs last in both directions.
        """
        stmt = select(User).options(selectinload(User.roles))
        count_stmt = select(func.count()).select_from(User)

        conditions = []
        if search:
            pattern = f"%{search}%"
            conditions.append(
                or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
            )
        if status == "active":
            conditions.append(User.is_active.is_(True))
        elif status == "disabled":
            conditions.append(User.is_active.is_(False))
        if verified == "yes":
            conditions.append(User.is_verified.is_(True))
        elif verified == "no":
            conditions.append(User.is_verified.is_(False))
        if role_name:
            subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role_name)
            )
            conditions.append(User.id.in_(subq))

        if conditions:
            for cond in conditions:
                stmt = stmt.where(cond)
                count_stmt = count_stmt.where(cond)

        total = (await self._db.execute(count_stmt)).scalar_one()

        sort_col = {
            "email": User.email,
            "last_login_at": User.last_login_at,
            "created_at": User.created_at,
        }.get(sort, User.email)
        if sort == "last_login_at":
            # Always NULLs last — admins picking recency don't want never-logged-in on top
            order_clause = (
                sort_col.desc().nulls_last() if order == "desc" else sort_col.asc().nulls_last()
            )
        else:
            order_clause = sort_col.desc() if order == "desc" else sort_col.asc()
        stmt = stmt.order_by(order_clause).offset((page - 1) * per_page).limit(per_page)

        rows = (await self._db.execute(stmt)).scalars().all()
        items = [await self.to_list_item(u) for u in rows]
        return items, total
```

- [ ] **Step 2.6: Run filter tests — must pass**

Run: `uv run pytest modules/users/tests/test_service.py -k "list_users_status or list_users_role or list_users_verified or list_users_sort" -v`

Expected: all PASS.

- [ ] **Step 2.7: Run full users test suite — must stay green**

Run: `uv run pytest modules/users/tests/ -q`

Expected: all pass. Pre-existing callers use `list_users(page=..., per_page=..., search=...)` which still match.

- [ ] **Step 2.8: Commit**

```bash
git add modules/users/users/service.py modules/users/tests/test_service.py
git commit -m "feat(users): add status/role/verified filters + sort to list_users"
```

---

## Task 3: Admin list endpoint query params

**Files:**
- Modify: `modules/users/users/endpoints/api_admin.py:34-43`
- Test: `modules/users/tests/test_api_admin.py`

Endpoint parses query params, coerces unknown enum values to defaults, then delegates to service.

- [ ] **Step 3.1: Write failing endpoint filter test**

Append to `modules/users/tests/test_api_admin.py` (outside existing `TestAdminList`, or a new class `TestAdminListFilters`):

```python
class TestAdminListFilters:
    @pytest.mark.anyio
    async def test_status_filter(self, admin_client, users_db):
        await _make_user(users_db, email="on@x.com")
        # Build a disabled user directly
        from datetime import UTC, datetime
        u = await _make_user(users_db, email="off@x.com")
        u.is_active = False
        u.disabled_at = datetime.now(UTC)
        await users_db.commit()

        resp = await admin_client.get("/api/users/admin?status=disabled")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "off@x.com" in emails
        assert "on@x.com" not in emails

    @pytest.mark.anyio
    async def test_unknown_status_returns_200_unfiltered(self, admin_client, users_db):
        await _make_user(users_db, email="any@x.com")
        resp = await admin_client.get("/api/users/admin?status=bogus")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "any@x.com" in emails

    @pytest.mark.anyio
    async def test_sort_last_login_desc(self, admin_client, users_db):
        from datetime import UTC, datetime, timedelta
        now = datetime.now(UTC)
        a = await _make_user(users_db, email="alpha@x.com")
        b = await _make_user(users_db, email="beta@x.com")
        a.last_login_at = now - timedelta(days=1)
        b.last_login_at = now
        await users_db.commit()

        resp = await admin_client.get(
            "/api/users/admin?sort=last_login_at&order=desc&per_page=50"
        )
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert emails.index("beta@x.com") < emails.index("alpha@x.com")
```

- [ ] **Step 3.2: Run — must fail** (endpoint ignores the new params)

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminListFilters -v`

Expected: FAIL — filter doesn't apply, sort doesn't apply.

- [ ] **Step 3.3: Extend `admin_list_users` to accept + coerce params**

Replace `modules/users/users/endpoints/api_admin.py:34-43` with:

```python
_ALLOWED_STATUS = {"active", "disabled"}
_ALLOWED_VERIFIED = {"yes", "no"}
_ALLOWED_SORT = {"email", "last_login_at", "created_at"}
_ALLOWED_ORDER = {"asc", "desc"}


@admin_router.get("", response_model=list[UserListItem])
async def admin_list_users(
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    verified: str | None = None,
    sort: str = "email",
    order: str = "asc",
    service: UserService = Depends(get_user_service),
):
    """List all users (paginated, optional search/filter/sort)."""
    items, _ = await service.list_users(
        page=page,
        per_page=per_page,
        search=q,
        status=status if status in _ALLOWED_STATUS else None,
        role_name=role or None,
        verified=verified if verified in _ALLOWED_VERIFIED else None,
        sort=sort if sort in _ALLOWED_SORT else "email",
        order=order if order in _ALLOWED_ORDER else "asc",
    )
    return items
```

Note: `status` is also a FastAPI `status` import at the top of the file. Rename the import to avoid the shadow — it's only used for `status.HTTP_201_CREATED`. Change `from fastapi import APIRouter, Depends, HTTPException, Request, status` to:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
```

and update `status_code=status.HTTP_201_CREATED` → `status_code=http_status.HTTP_201_CREATED`.

- [ ] **Step 3.4: Run filter tests — must pass**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminListFilters -v`

Expected: all PASS.

- [ ] **Step 3.5: Run full api_admin suite — must stay green**

Run: `uv run pytest modules/users/tests/test_api_admin.py -q`

Expected: all pass.

- [ ] **Step 3.6: Commit**

```bash
git add modules/users/users/endpoints/api_admin.py modules/users/tests/test_api_admin.py
git commit -m "feat(users): admin list endpoint accepts status/role/verified/sort/order"
```

---

## Task 4: Admin index view echoes filter params

**Files:**
- Modify: `modules/users/users/endpoints/views.py:110-132`
- Test: `modules/users/tests/test_views.py`

The Inertia view renders with the full query echoed in props so the frontend can show current filter state.

- [ ] **Step 4.1: Write failing view filter test**

Append to `modules/users/tests/test_views.py` (colocated with existing admin view tests):

```python
class TestAdminIndexFilters:
    @pytest.mark.anyio
    async def test_status_filter_in_view(self, admin_client, users_db):
        await _make_user(users_db, email="on-view@x.com")
        u = await _make_user(users_db, email="off-view@x.com")
        u.is_active = False
        await users_db.commit()

        resp = await admin_client.get(
            "/users/admin?status=disabled",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        props = resp.json()["props"]
        emails = [u["email"] for u in props["users"]]
        assert "off-view@x.com" in emails
        assert "on-view@x.com" not in emails
        # Echoed back so the frontend can show current state
        assert props["filters"]["status"] == "disabled"
        assert props["filters"]["sort"] == "email"
        assert props["filters"]["order"] == "asc"
```

Check if `_make_user` helper exists in `test_views.py` — if not, import from `test_api_admin` or recreate the minimal version. (Confirm during implementation; if missing, add a fixture `make_user` or inline the User creation.)

- [ ] **Step 4.2: Run — must fail**

Run: `uv run pytest modules/users/tests/test_views.py::TestAdminIndexFilters -v`

Expected: FAIL (props don't include `filters`, status filter not applied).

- [ ] **Step 4.3: Extend `admin_index` view**

Replace `modules/users/users/endpoints/views.py:110-132` with:

```python
@router.get(
    "/admin",
    response_model=None,
    dependencies=[Depends(RequiresPermission("users.manage"))],
)
async def admin_index(
    request: Request,
    inertia: InertiaDep,
    service: UserService = Depends(get_user_service),
    page: int = 1,
    per_page: int = 20,
    q: str | None = None,
    status: str | None = None,
    role: str | None = None,
    verified: str | None = None,
    sort: str = "email",
    order: str = "asc",
) -> InertiaResponse:
    from users.endpoints.api_admin import (
        _ALLOWED_ORDER,
        _ALLOWED_SORT,
        _ALLOWED_STATUS,
        _ALLOWED_VERIFIED,
    )

    clean_status = status if status in _ALLOWED_STATUS else None
    clean_verified = verified if verified in _ALLOWED_VERIFIED else None
    clean_sort = sort if sort in _ALLOWED_SORT else "email"
    clean_order = order if order in _ALLOWED_ORDER else "asc"

    users, total = await service.list_users(
        page=page,
        per_page=per_page,
        search=q,
        status=clean_status,
        role_name=role or None,
        verified=clean_verified,
        sort=clean_sort,
        order=clean_order,
    )
    return await inertia.render(
        "Users/Users/Index",
        {
            "users": [u.model_dump(mode="json") for u in users],
            "pagination": {"page": page, "per_page": per_page, "total": total},
            "query": q or "",
            "filters": {
                "status": clean_status or "all",
                "role": role or "",
                "verified": clean_verified or "all",
                "sort": clean_sort,
                "order": clean_order,
            },
            "roles": await _roles_payload(request.app),
        },
    )
```

- [ ] **Step 4.4: Run filter test — must pass**

Run: `uv run pytest modules/users/tests/test_views.py::TestAdminIndexFilters -v`

Expected: PASS.

- [ ] **Step 4.5: Run full view suite — must stay green**

Run: `uv run pytest modules/users/tests/test_views.py -q`

Expected: all pass.

- [ ] **Step 4.6: Commit**

```bash
git add modules/users/users/endpoints/views.py modules/users/tests/test_views.py
git commit -m "feat(users): admin index view accepts + echoes filter params"
```

---

## Task 5: Verify endpoint + service method

**Files:**
- Modify: `modules/users/users/service.py`
- Modify: `modules/users/users/endpoints/api_admin.py`
- Test: `modules/users/tests/test_service.py`, `modules/users/tests/test_api_admin.py`

- [ ] **Step 5.1: Write failing service test**

Append to `test_service.py`:

```python
async def test_mark_verified_sets_flag_and_is_idempotent(users_db):
    """mark_verified returns the user with is_verified=True; repeating is a no-op."""
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    from fastapi_users.password import PasswordHelper
    from users.models import User

    pw = PasswordHelper()
    user = User(
        id=_uuid.uuid4(), email="unv@x.com", hashed_password=pw.hash("x"),
        is_active=True, is_superuser=False, is_verified=False,
    )
    users_db.add(user)
    await users_db.flush()

    svc = UserService(users_db, UserManager(None))
    out = await svc.mark_verified(user.id)
    assert out.is_verified is True

    # Idempotent
    out2 = await svc.mark_verified(user.id)
    assert out2.is_verified is True


async def test_mark_verified_unknown_raises(users_db):
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.service import UserService
    import uuid as _uuid
    import pytest as _pytest

    svc = UserService(users_db, UserManager(None))
    with _pytest.raises(UserNotFoundError):
        await svc.mark_verified(_uuid.uuid4())
```

- [ ] **Step 5.2: Run — must fail** (`mark_verified` does not exist)

Run: `uv run pytest modules/users/tests/test_service.py -k mark_verified -v`

Expected: FAIL with AttributeError.

- [ ] **Step 5.3: Add `mark_verified` to `UserService`**

Insert in `modules/users/users/service.py` after the `enable` method (around line 143):

```python
    async def mark_verified(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        if not user.is_verified:
            user.is_verified = True
            await self._db.flush()
        return user
```

- [ ] **Step 5.4: Run — must pass**

Run: `uv run pytest modules/users/tests/test_service.py -k mark_verified -v`

Expected: PASS.

- [ ] **Step 5.5: Write failing endpoint test**

Append to `test_api_admin.py`:

```python
class TestAdminVerify:
    @pytest.mark.anyio
    async def test_verify_sets_flag(self, admin_client, users_db):
        u = await _make_user(users_db, email="toverify@x.com", verified=False)
        resp = await admin_client.patch(f"/api/users/admin/{u.id}/verify")
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True

    @pytest.mark.anyio
    async def test_verify_idempotent(self, admin_client, users_db):
        u = await _make_user(users_db, email="already@x.com", verified=True)
        resp = await admin_client.patch(f"/api/users/admin/{u.id}/verify")
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True

    @pytest.mark.anyio
    async def test_verify_unknown_returns_404(self, admin_client):
        import uuid as _uuid
        resp = await admin_client.patch(f"/api/users/admin/{_uuid.uuid4()}/verify")
        assert resp.status_code == 404
```

- [ ] **Step 5.6: Run — must fail** (endpoint does not exist → 404 already, but `test_verify_sets_flag` should fail because user stays unverified)

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminVerify -v`

Expected: `test_verify_sets_flag` and `test_verify_idempotent` FAIL (404). `test_verify_unknown_returns_404` accidentally passes (there's no route). We'll rely on the first two failing to prove the route is needed.

- [ ] **Step 5.7: Add endpoint**

Append to `modules/users/users/endpoints/api_admin.py` (before the final blank line):

```python
@admin_router.patch("/{user_id}/verify", response_model=UserListItem)
async def admin_mark_verified(
    user_id: uuid.UUID,
    service: UserService = Depends(get_user_service),
):
    """Mark a user verified. Idempotent."""
    try:
        user = await service.mark_verified(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    return await service.to_list_item(user)
```

- [ ] **Step 5.8: Run — must pass**

Run: `uv run pytest modules/users/tests/test_api_admin.py::TestAdminVerify -v`

Expected: all three PASS.

- [ ] **Step 5.9: Run full users suite**

Run: `uv run pytest modules/users/tests/ -q`

Expected: all pass.

- [ ] **Step 5.10: Commit**

```bash
git add modules/users/users/service.py modules/users/users/endpoints/api_admin.py modules/users/tests/test_service.py modules/users/tests/test_api_admin.py
git commit -m "feat(users): PATCH /admin/{id}/verify (admin mark-verified)"
```

---

## Task 6: Detail page passes `has_permissions_module` flag

**Files:**
- Modify: `modules/users/users/endpoints/views.py` (`admin_edit_page`)
- Test: `modules/users/tests/test_views.py`

- [ ] **Step 6.1: Write failing view test**

Append to `test_views.py`:

```python
class TestAdminEditCrosslink:
    @pytest.mark.anyio
    async def test_flag_true_when_permissions_installed(self, admin_client, users_db, app):
        # Fake that the permissions module is installed by stubbing app.state.sm.modules
        class _FakeMeta:
            name = "Permissions"
        class _FakeMod:
            meta = _FakeMeta()
        original = app.state.sm.modules
        app.state.sm = app.state.sm._replace(modules=(*original, _FakeMod()))
        try:
            u = await _make_user(users_db, email="crosslink@x.com")
            resp = await admin_client.get(
                f"/users/admin/{u.id}",
                headers={"X-Inertia": "true", "Accept": "application/json"},
            )
            assert resp.status_code == 200
            assert resp.json()["props"]["has_permissions_module"] is True
        finally:
            app.state.sm = app.state.sm._replace(modules=original)

    @pytest.mark.anyio
    async def test_flag_false_when_not_installed(self, admin_client, users_db):
        u = await _make_user(users_db, email="nocrosslink@x.com")
        resp = await admin_client.get(
            f"/users/admin/{u.id}",
            headers={"X-Inertia": "true", "Accept": "application/json"},
        )
        assert resp.status_code == 200
        # By default the test fixture doesn't install Permissions
        assert resp.json()["props"]["has_permissions_module"] is False
```

Check `app.state.sm` shape during implementation — if it's a `Services` namedtuple, `_replace` works; if it's a dataclass, use `dataclasses.replace`. Adjust the fake accordingly.

- [ ] **Step 6.2: Run — must fail**

Run: `uv run pytest modules/users/tests/test_views.py::TestAdminEditCrosslink -v`

Expected: FAIL with KeyError on `has_permissions_module`.

- [ ] **Step 6.3: Extend `admin_edit_page`**

In `modules/users/users/endpoints/views.py`, update `admin_edit_page` (around line 157):

```python
@router.get(
    "/admin/{user_id}",
    response_model=None,
    dependencies=[Depends(RequiresPermission("users.manage"))],
)
async def admin_edit_page(
    user_id: str,
    request: Request,
    inertia: InertiaDep,
    service: UserService = Depends(get_user_service),
) -> InertiaResponse:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    try:
        user_item = await service.get_list_item(uid)
    except UserNotFoundError:
        raise HTTPException(status_code=404) from None

    has_permissions = any(
        m.meta.name == "Permissions" for m in request.app.state.sm.modules
    )

    return await inertia.render(
        "Users/Users/Edit",
        {
            "user": user_item.model_dump(mode="json"),
            "roles": await _roles_payload(request.app),
            "has_permissions_module": has_permissions,
        },
    )
```

- [ ] **Step 6.4: Run — must pass**

Run: `uv run pytest modules/users/tests/test_views.py::TestAdminEditCrosslink -v`

Expected: PASS.

- [ ] **Step 6.5: Run full users suite + lint**

Run:
```bash
uv run pytest modules/users/tests/ -q
make lint
```

Expected: tests pass; lint passes (ignore pre-existing TS failures if any — confirm they match the baseline from the start of sub-project 2).

- [ ] **Step 6.6: Commit**

```bash
git add modules/users/users/endpoints/views.py modules/users/tests/test_views.py
git commit -m "feat(users): expose has_permissions_module flag on admin detail page"
```

---

## Task 7: Frontend — filter controls on Index

**Files:**
- Modify: `modules/users/users/pages/Users/Index.tsx`

No frontend tests in this codebase for these pages. We rely on manual + Playwright smoke.

- [ ] **Step 7.1: Rewrite `Index.tsx`**

Replace `modules/users/users/pages/Users/Index.tsx` with:

```tsx
import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { ArrowDown, ArrowUp, Pencil, Plus, Search, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
}

interface Filters {
  status: 'all' | 'active' | 'disabled';
  role: string;
  verified: 'all' | 'yes' | 'no';
  sort: 'email' | 'last_login_at' | 'created_at';
  order: 'asc' | 'desc';
}

interface Props {
  users: UserListItem[];
  pagination: Pagination;
  query: string;
  filters: Filters;
  roles: { id: string; name: string }[];
}

function Index() {
  const {
    users,
    pagination,
    query: initialQuery,
    filters,
    roles,
  } = usePage<{ props: Props }>().props as unknown as Props;

  const [search, setSearch] = useState(initialQuery ?? '');

  const navigate = useCallback(
    (next: Partial<{ page: number; q: string } & Filters>) => {
      const params: Record<string, string> = {};
      const q = next.q ?? search;
      const status = next.status ?? filters.status;
      const role = next.role ?? filters.role;
      const verified = next.verified ?? filters.verified;
      const sort = next.sort ?? filters.sort;
      const order = next.order ?? filters.order;
      const page = next.page ?? 1;
      if (q) params.q = q;
      if (status !== 'all') params.status = status;
      if (role) params.role = role;
      if (verified !== 'all') params.verified = verified;
      if (sort !== 'email') params.sort = sort;
      if (order !== 'asc') params.order = order;
      if (page > 1) params.page = String(page);
      router.get('/users/admin', params, { preserveState: true, preserveScroll: true });
    },
    [search, filters],
  );

  useEffect(() => {
    if (search === (initialQuery ?? '')) return;
    const timeout = setTimeout(() => navigate({ q: search, page: 1 }), 300);
    return () => clearTimeout(timeout);
  }, [search, initialQuery, navigate]);

  const totalPages = Math.ceil(pagination.total / pagination.per_page);

  const toggleSort = (col: Filters['sort']) => {
    if (filters.sort === col) {
      navigate({ order: filters.order === 'asc' ? 'desc' : 'asc' });
    } else {
      navigate({ sort: col, order: 'asc' });
    }
  };

  const SortIcon = ({ col }: { col: Filters['sort'] }) =>
    filters.sort !== col ? null : filters.order === 'asc' ? (
      <ArrowUp className="inline size-3 ml-1" />
    ) : (
      <ArrowDown className="inline size-3 ml-1" />
    );

  return (
    <PageShell
      title="Users"
      description="Manage user accounts and roles"
      actions={
        <Button asChild>
          <Link href="/users/admin/invite">
            <Plus />
            Invite user
          </Link>
        </Button>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative max-w-sm flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search by email or name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          value={filters.status}
          onValueChange={(v) => navigate({ status: v as Filters['status'], page: 1 })}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="disabled">Disabled</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={filters.role || 'all'}
          onValueChange={(v) => navigate({ role: v === 'all' ? '' : v, page: 1 })}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            {roles.map((r) => (
              <SelectItem key={r.id} value={r.name}>
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.verified}
          onValueChange={(v) => navigate({ verified: v as Filters['verified'], page: 1 })}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All verified</SelectItem>
            <SelectItem value="yes">Verified</SelectItem>
            <SelectItem value="no">Unverified</SelectItem>
          </SelectContent>
        </Select>
        {pagination.total > 0 && (
          <p className="text-sm text-muted-foreground whitespace-nowrap ml-auto">
            {pagination.total} user{pagination.total !== 1 ? 's' : ''}
          </p>
        )}
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                <button onClick={() => toggleSort('email')} className="font-medium">
                  Email
                  <SortIcon col="email" />
                </button>
              </TableHead>
              <TableHead className="hidden md:table-cell">Name</TableHead>
              <TableHead className="hidden sm:table-cell">Roles</TableHead>
              <TableHead className="hidden sm:table-cell">Status</TableHead>
              <TableHead className="hidden lg:table-cell">
                <button onClick={() => toggleSort('last_login_at')} className="font-medium">
                  Last login
                  <SortIcon col="last_login_at" />
                </button>
              </TableHead>
              <TableHead className="hidden xl:table-cell">
                <button onClick={() => toggleSort('created_at')} className="font-medium">
                  Created
                  <SortIcon col="created_at" />
                </button>
              </TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>
                  <div>
                    <span className="font-medium">{user.email}</span>
                    {!user.is_verified && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        unverified
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell className="hidden md:table-cell text-muted-foreground text-sm">
                  {user.full_name || '—'}
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {user.roles.length > 0 ? (
                      user.roles.map((r) => (
                        <Badge key={r} variant="secondary">
                          {r}
                        </Badge>
                      ))
                    ) : (
                      <span className="text-muted-foreground text-sm">—</span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Badge variant={user.is_active ? 'secondary' : 'destructive'}>
                    {user.is_active ? 'Active' : 'Disabled'}
                  </Badge>
                </TableCell>
                <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                  {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString() : '—'}
                </TableCell>
                <TableCell className="hidden xl:table-cell text-sm text-muted-foreground">
                  {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild variant="ghost" size="icon-sm">
                    <Link href={`/users/admin/${user.id}`}>
                      <Pencil />
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {users.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <Users className="size-8" />
                    <p>{search ? `No users match "${search}"` : 'No users match these filters'}</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={pagination.page <= 1}
            onClick={() => navigate({ page: pagination.page - 1 })}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {pagination.page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={pagination.page >= totalPages}
            onClick={() => navigate({ page: pagination.page + 1 })}
          >
            Next
          </Button>
        </div>
      )}
    </PageShell>
  );
}

Index.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Index;
```

Confirm `Select` component exists in `packages/ui/src/components/ui/select.tsx` before this step; if not, note it as blocked and notify. (It is present as of origin/main — verify during implementation.)

- [ ] **Step 7.2: Verify file size cap**

Run: `uv run python scripts/check_file_size.py` (or `make lint`).

Expected: `Index.tsx` stays under 300 lines. If over, split filter-controls into a sibling component (e.g. `Users/IndexFilters.tsx`).

- [ ] **Step 7.3: Manual smoke**

- [ ] `make dev` → log in as admin → `/users/admin` → verify filters + sort URL-sync works.

- [ ] **Step 7.4: Commit**

```bash
git add modules/users/users/pages/Users/Index.tsx
git commit -m "feat(users): filter + sort controls on admin list"
```

---

## Task 8: Frontend — detail page Metadata, confirmations, verify action, crosslink

**Files:**
- Modify: `modules/users/users/pages/Users/Edit.tsx`

- [ ] **Step 8.1: Rewrite `Edit.tsx`**

Replace `modules/users/users/pages/Users/Edit.tsx` with:

```tsx
import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
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
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import { Checkbox } from '@simple-module-py/ui/components/ui/checkbox';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { fetchWithCsrf } from '@simple-module-py/ui/lib/csrf';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  disabled_at: string | null;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Role {
  id: string;
  name: string;
}

interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
}

function fmt(dt: string | null): string {
  if (!dt) return '—';
  return new Date(dt).toLocaleString();
}

function Edit() {
  const { user, roles, has_permissions_module } = usePage<{ props: Props }>()
    .props as unknown as Props;

  const [isActive, setIsActive] = useState(user.is_active);
  const [isVerified, setIsVerified] = useState(user.is_verified);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(user.roles ?? []);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingRoles, setSavingRoles] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const disableAccount = () => {
    setSavingStatus(true);
    fetchWithCsrf(`/api/users/admin/${user.id}/disable`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsActive(false);
          toast.success('User disabled');
        } else {
          toast.error('Failed to disable user');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingStatus(false));
  };

  const enableAccount = () => {
    setSavingStatus(true);
    fetchWithCsrf(`/api/users/admin/${user.id}/enable`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsActive(true);
          toast.success('User enabled');
        } else {
          toast.error('Failed to enable user');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingStatus(false));
  };

  const handleSaveRoles = () => {
    setSavingRoles(true);
    fetchWithCsrf(`/api/users/admin/${user.id}/roles`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role_names: selectedRoles }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Roles updated');
        } else {
          toast.error('Failed to update roles');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingRoles(false));
  };

  const copyResetLink = () => {
    fetchWithCsrf(`/api/users/admin/${user.id}/reset-password-link`, { method: 'POST' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          await navigator.clipboard.writeText(data.link ?? data.url ?? '');
          toast.success('Reset link copied to clipboard');
        } else {
          toast.error('Failed to generate reset link');
        }
      })
      .catch(() => toast.error('An error occurred'));
  };

  const markVerified = () => {
    setSavingVerify(true);
    fetchWithCsrf(`/api/users/admin/${user.id}/verify`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsVerified(true);
          toast.success('User marked verified');
        } else {
          toast.error('Failed to mark verified');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingVerify(false));
  };

  const handleReload = () => {
    router.reload();
  };

  return (
    <PageShell
      title={user.email}
      description={user.full_name ?? 'Edit user account'}
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">Back to Users</Link>
        </Button>
      }
    >
      <div className="space-y-6 max-w-xl">
        {/* Metadata card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Metadata</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <span className="text-muted-foreground">Created</span>
            <span>{fmt(user.created_at)}</span>
            <span className="text-muted-foreground">Last login</span>
            <span>{user.last_login_at ? fmt(user.last_login_at) : 'Never'}</span>
            <span className="text-muted-foreground">Disabled at</span>
            <span>{fmt(user.disabled_at)}</span>
            <span className="text-muted-foreground">Verified</span>
            <span className="flex items-center gap-2">
              {isVerified ? (
                'Yes'
              ) : (
                <>
                  No
                  <Button size="sm" variant="outline" onClick={markVerified} disabled={savingVerify}>
                    {savingVerify ? 'Saving…' : 'Mark verified'}
                  </Button>
                </>
              )}
            </span>
          </CardContent>
        </Card>

        {/* Status card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge variant={isActive ? 'secondary' : 'destructive'}>
                {isActive ? 'Active' : 'Disabled'}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {isActive ? (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm" disabled={savingStatus}>
                      {savingStatus ? 'Saving…' : 'Disable account'}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Disable {user.email}?</AlertDialogTitle>
                      <AlertDialogDescription>
                        They won't be able to sign in until you re-enable the account.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={disableAccount}>Disable</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : (
                <Button size="sm" onClick={enableAccount} disabled={savingStatus}>
                  {savingStatus ? 'Saving…' : 'Enable account'}
                </Button>
              )}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    Copy reset-password link
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Generate reset link for {user.email}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      A one-time password-reset URL will be copied to your clipboard.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={copyResetLink}>Generate</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </CardContent>
        </Card>

        {/* Roles card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Roles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-col gap-2">
              {roles.map((role) => (
                <div key={role.id} className="flex items-center gap-2">
                  <Checkbox
                    id={`role-${role.id}`}
                    checked={selectedRoles.includes(role.name)}
                    onCheckedChange={() => toggleRole(role.name)}
                  />
                  <Label htmlFor={`role-${role.id}`} className="cursor-pointer font-normal">
                    {role.name}
                  </Label>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveRoles} disabled={savingRoles}>
                {savingRoles ? 'Saving…' : 'Save roles'}
              </Button>
              <Button size="sm" variant="ghost" onClick={handleReload}>
                Discard
              </Button>
            </div>
          </CardContent>
        </Card>

        {has_permissions_module && (
          <Link
            href={`/permissions/users/${user.id}`}
            className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
          >
            <ShieldCheck className="size-4" />
            Manage permissions →
          </Link>
        )}
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
```

Confirm `AlertDialog` is present at `packages/ui/src/components/ui/alert-dialog.tsx` before this step. If missing, `npx shadcn@latest add alert-dialog` or flag as blocked.

- [ ] **Step 8.2: Verify file size cap**

Run: `uv run python scripts/check_file_size.py` (or `make lint`).

Expected: `Edit.tsx` stays under 300 lines. If over, extract one of the cards (e.g. `MetadataCard.tsx` or split the AlertDialog blocks into a helper).

- [ ] **Step 8.3: Manual smoke**

- [ ] `make dev` → admin → open a user → confirm:
  - Metadata card shows created/last-login/disabled-at/verified.
  - `Mark verified` button appears only when the user isn't verified; clicking it updates the card.
  - `Disable account` opens a confirm dialog; Cancel aborts, Disable performs the action.
  - `Copy reset-password link` opens a confirm dialog.
  - When the Permissions module is installed, `Manage permissions →` link appears and navigates to `/permissions/users/{id}`.

- [ ] **Step 8.4: Commit**

```bash
git add modules/users/users/pages/Users/Edit.tsx
git commit -m "feat(users): metadata card, verify action, confirmations, permissions crosslink"
```

---

## Task 9: Final validation

- [ ] **Step 9.1: Full test suite**

Run:
```bash
uv run pytest modules/users/tests/ -q
uv run pytest -q  # repo-wide
```

Expected: all pass.

- [ ] **Step 9.2: Lint + doctor**

Run:
```bash
make lint
make doctor
```

Expected: lint passes (document any pre-existing TS failure matched to merge baseline); doctor exit 0.

- [ ] **Step 9.3: Confirm public-contract invariants**

- [ ] `UserListItem` gained `created_at`; no other field removed.
- [ ] `GET /api/users/admin` still accepts `page`, `per_page`, `q` and returns the same shape.
- [ ] `PATCH /admin/{id}/disable|enable`, `PUT /admin/{id}/roles`, `POST /admin/{id}/reset-password-link` unchanged.
- [ ] Inertia page names `Users/Users/Index`, `Users/Users/Edit` preserved.
- [ ] Event publication timing unchanged (UserInvited/UserDisabled/RoleAssigned).

If all green, this sub-project is shippable. No single commit; feature branch is merge-ready per the branch discipline the user is on.
