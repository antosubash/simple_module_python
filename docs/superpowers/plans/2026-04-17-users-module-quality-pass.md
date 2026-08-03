# Users Module — Quality Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pay down 8 code-quality issues in `modules/users` — service-layer convention violations, naming collisions, layering leaks, stale comments, duplicated helpers — without changing any externally observable behavior.

**Architecture:** Behavior-preserving refactor. Add a `users/exceptions.py` with `UserNotFoundError` so the service raises domain exceptions instead of `HTTPException`. Endpoints translate at the boundary. Service stops calling `.commit()` and relies on the framework's per-request auto-commit via `after_flush`. Rename `services.py` → `state.py` (`UsersServices` → `UsersState`) to disambiguate from `service.py` (`UserService`). Split `test_models.py` by model.

**Tech Stack:** Python 3.12, FastAPI, SQLModel/SQLAlchemy async, fastapi-users, pytest with `anyio`, uv workspaces.

**Reference spec:** [docs/superpowers/specs/2026-04-17-users-module-quality-pass-design.md](../specs/2026-04-17-users-module-quality-pass-design.md)

**Conventions reminder:**
- 300-line cap on `.py`/`.ts`/`.tsx` (CI-enforced).
- Service code must not call `session.commit()` — flush only.
- `framework/*` → plugin import is `SM009` error; plugin → framework is fine.
- Run `make test-py` after each mutation of the users package; `make lint` before any commit.

---

## Task 1: Clean up stale comments (item 5)

**Files:**
- Modify: `modules/users/users/module.py:1`
- Modify: `modules/users/users/endpoints/api.py:102`

Trivial. No tests — these are comment edits.

- [ ] **Step 1: Read current docstring and comments**

```bash
head -5 modules/users/users/module.py
```
Expect: `"""Users module — local user management (replaces Keycloak)."""`

```bash
sed -n '100,105p' modules/users/users/endpoints/api.py
```
Expect the `AuthMiddleware (once wired in Task 8)` comment.

- [ ] **Step 2: Rewrite `module.py` docstring**

Use Edit to replace `"""Users module — local user management (replaces Keycloak)."""` with:

```python
"""Users module — local-account authentication and user management."""
```

- [ ] **Step 3: Rewrite `api.py:102` comment**

Use Edit to replace:

```python
    # Bridge the session cookie — AuthMiddleware (once wired in Task 8) reads this
```

with:

```python
    # Bridge the session cookie — AuthMiddleware reads this
```

- [ ] **Step 4: Verify lint + tests still pass**

```bash
make lint && make test-py
```
Expect: all green.

- [ ] **Step 5: Commit**

```bash
git add modules/users/users/module.py modules/users/users/endpoints/api.py
git commit -m "docs(users): remove stale Keycloak + Task 8 references"
```

---

## Task 2: Extract `_roles_payload` helper in `views.py` (item 7, TDD)

**Files:**
- Modify: `modules/users/users/endpoints/views.py`
- Test: `modules/users/tests/test_views.py`

Three admin view handlers (`admin_index`, `admin_invite_page`, `admin_edit_page`) each build the same `[{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]` list. Extract once.

- [ ] **Step 1: Write the failing test**

Add to `modules/users/tests/test_views.py`:

```python
@pytest.mark.anyio
async def test_roles_payload_returns_id_name_dicts(users_app):
    """Helper reads the roles cache and returns id/name dicts in cache order."""
    from users.endpoints.views import _roles_payload

    payload = await _roles_payload(users_app)

    assert isinstance(payload, list)
    assert all(set(item.keys()) == {"id", "name"} for item in payload)
    names = [item["name"] for item in payload]
    assert "admin" in names
    assert "user" in names
```

- [ ] **Step 2: Run test — expect failure**

```bash
uv run pytest modules/users/tests/test_views.py::test_roles_payload_returns_id_name_dicts -v
```
Expect: FAIL with `ImportError: cannot import name '_roles_payload' from 'users.endpoints.views'`.

- [ ] **Step 3: Implement the helper**

Add to `modules/users/users/endpoints/views.py` near the imports section (after `router = APIRouter()`):

```python
async def _roles_payload(app) -> list[dict[str, str]]:
    """Shape roles-cache entries for Inertia props."""
    return [{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]
```

- [ ] **Step 4: Replace the three inline comprehensions with helper calls**

In `admin_index`, `admin_invite_page`, `admin_edit_page`, replace:

```python
"roles": [{"id": r.id, "name": r.name} for r in await get_roles_cache(request.app)],
```

with:

```python
"roles": await _roles_payload(request.app),
```

- [ ] **Step 5: Run the new test — expect pass**

```bash
uv run pytest modules/users/tests/test_views.py::test_roles_payload_returns_id_name_dicts -v
```
Expect: PASS.

- [ ] **Step 6: Run full users test suite**

```bash
make test-py
```
Expect: all green (no other test broke).

- [ ] **Step 7: Run lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 8: Commit**

```bash
git add modules/users/users/endpoints/views.py modules/users/tests/test_views.py
git commit -m "refactor(users): extract _roles_payload helper in views"
```

---

## Task 3: Promote function-scope imports (item 8)

**Files:**
- Modify: `modules/users/users/bootstrap.py`

`PasswordHelper` is imported inside `create_admin` and `create_standard_user` via `from fastapi_users.password import PasswordHelper`. It's not optional — the module has hard dep on `fastapi-users`. Promote to top-level.

Note: `deps.py` also has `from users.service import UserService` inside `get_user_service` — that one is genuinely needed to break an import cycle (service.py → contracts; deps.py is imported at app startup; keeping it lazy is intentional). Leave it alone.

- [ ] **Step 1: Read current imports**

```bash
head -20 modules/users/users/bootstrap.py
```
Expect to see the top-level imports; `PasswordHelper` is NOT there.

- [ ] **Step 2: Add `PasswordHelper` to top-level imports**

Use Edit to add after `from users.settings import UsersSettings`:

```python
from fastapi_users.password import PasswordHelper
```

(Place it alphabetically with other `fastapi_users` imports if any; otherwise group with third-party imports.)

- [ ] **Step 3: Remove lazy imports from functions**

Remove `from fastapi_users.password import PasswordHelper` and the surrounding comment block from inside `create_admin` (around line 46) and from inside `create_standard_user` (around line 127).

- [ ] **Step 4: Run bootstrap tests**

```bash
uv run pytest modules/users/tests/test_bootstrap.py -v
```
Expect: all green.

- [ ] **Step 5: Run full users test suite**

```bash
make test-py
```
Expect: all green.

- [ ] **Step 6: Lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 7: Commit**

```bash
git add modules/users/users/bootstrap.py
git commit -m "refactor(users): promote PasswordHelper import to module top"
```

---

## Task 4: Add `UserNotFoundError` and `_require_user` helper (items 3 + 4, TDD)

**Files:**
- Create: `modules/users/users/exceptions.py`
- Modify: `modules/users/users/service.py`
- Create: `modules/users/tests/test_service.py`

This is the boundary shift. Service raises `UserNotFoundError` instead of `HTTPException`. Endpoints translate in Task 5.

- [ ] **Step 1: Write failing test for the exception + `_require_user` behavior**

Create `modules/users/tests/test_service.py`:

```python
"""Tests for UserService domain-level error behavior."""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.anyio
async def test_disable_unknown_user_raises_user_not_found(users_app):
    """disable() with an unknown UUID raises UserNotFoundError (not HTTPException)."""
    from users.deps import get_user_service
    from users.exceptions import UserNotFoundError

    async with users_app.state.sm.db.session_factory() as session:
        # Build the service directly (bypass FastAPI Depends).
        from users.db_adapter import UserDatabaseWithRoles
        from users.manager import UserManager
        from users.models import User
        from users.service import UserService

        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        service = UserService(session, manager)

        with pytest.raises(UserNotFoundError):
            await service.disable(uuid.uuid4())


@pytest.mark.anyio
async def test_enable_unknown_user_raises_user_not_found(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        service = UserService(session, manager)

        with pytest.raises(UserNotFoundError):
            await service.enable(uuid.uuid4())


@pytest.mark.anyio
async def test_set_roles_unknown_user_raises_user_not_found(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        service = UserService(session, manager)

        with pytest.raises(UserNotFoundError):
            await service.set_roles(uuid.uuid4(), ["user"])


@pytest.mark.anyio
async def test_generate_reset_link_unknown_user_raises_user_not_found(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        service = UserService(session, manager)

        with pytest.raises(UserNotFoundError):
            await service.generate_reset_link(uuid.uuid4(), "http://testserver")


@pytest.mark.anyio
async def test_get_list_item_unknown_user_raises_user_not_found(users_app):
    from users.db_adapter import UserDatabaseWithRoles
    from users.exceptions import UserNotFoundError
    from users.manager import UserManager
    from users.models import User
    from users.service import UserService

    async with users_app.state.sm.db.session_factory() as session:
        user_db = UserDatabaseWithRoles(session, User)
        manager = UserManager(
            user_db,
            users_app.state.users.mailer,
            users_app.state.users.settings,
        )
        service = UserService(session, manager)

        with pytest.raises(UserNotFoundError):
            await service.get_list_item(uuid.uuid4())
```

- [ ] **Step 2: Run tests — expect failures**

```bash
uv run pytest modules/users/tests/test_service.py -v
```
Expect: 5 failures — `ImportError: cannot import name 'UserNotFoundError' from 'users.exceptions'` (and downstream: tests currently see `HTTPException`, not the new type).

- [ ] **Step 3: Create the exceptions module**

Create `modules/users/users/exceptions.py`:

```python
"""Domain-level exceptions raised by the users module.

Kept internal to the module — callers in the endpoints layer translate these
into HTTP responses. Not re-exported via ``contracts/`` because no other
module catches them today. Promote to contracts if that changes.
"""

from __future__ import annotations

import uuid


class UserNotFoundError(Exception):
    """Raised when a user lookup by id/email returns nothing."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(f"User {user_id} not found")
        self.user_id = user_id
```

- [ ] **Step 4: Add `_require_user` helper and switch service methods**

In `modules/users/users/service.py`:

a) Remove all `from fastapi import HTTPException` lazy-imports inside method bodies.

b) Add at top:

```python
from users.exceptions import UserNotFoundError
```

c) Add a private helper alongside `_get_user_with_roles`:

```python
async def _require_user(self, user_id: uuid.UUID) -> User:
    """Fetch a user with roles eager-loaded, or raise UserNotFoundError."""
    user = await self._get_user_with_roles(user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user
```

d) In `disable`, replace:

```python
user = await self._get_user_with_roles(user_id)
if user is None:
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="User not found")
```

with:

```python
user = await self._require_user(user_id)
```

Keep the rest of `disable` unchanged for now (still calls `.commit()` — Task 6 removes that).

e) Same replacement in `enable` (around the analogous block).

f) In `set_roles`, replace the identical block with `user = await self._require_user(user_id)`.

g) In `generate_reset_link`, replace the block with `user = await self._require_user(user_id)`.

h) In `get_list_item`, replace the block with `user = await self._require_user(user_id)`.

i) Where the method then does `refreshed = await self._get_user_with_roles(user_id); assert refreshed is not None`, you may now simplify to a single `_require_user` call, but only if behavior is unchanged — **keep the re-fetch in place for this task**; Task 6 revises the post-mutation path.

- [ ] **Step 5: Run service tests — expect pass**

```bash
uv run pytest modules/users/tests/test_service.py -v
```
Expect: 5 passes.

- [ ] **Step 6: Run full users test suite**

```bash
make test-py
```
Expect: **existing `test_api_admin.py::test_disable_nonexistent_returns_404` must still pass** — it asserts the endpoint returns 404. If the endpoint is still raising the un-caught `UserNotFoundError`, it won't — we fix that in Task 5.

**If the 404 test fails, that's expected at this point.** Continue to Task 5 before committing. Mark the plan item blocked with a note in the commit body when you do commit.

Actually — don't leave main broken between tasks. Instead, proceed directly to Task 5 and combine with Task 4 in a single commit.

- [ ] **Step 7: DO NOT commit yet** — proceed to Task 5. The commit happens at the end of Task 5 with both changes together, because Task 4 alone breaks the existing 404 tests.

---

## Task 5: Endpoints translate `UserNotFoundError` → 404 (item 3 continued)

**Files:**
- Modify: `modules/users/users/endpoints/api_admin.py`
- Modify: `modules/users/users/endpoints/views.py`
- Modify: `modules/users/tests/test_api_admin.py` (add endpoint-level coverage)
- Modify: `modules/users/tests/test_views.py` (add endpoint-level coverage)

The existing `test_disable_nonexistent_returns_404` test already verifies the translation. Add symmetric coverage for `enable`, `set_roles`, `reset-password-link`, and the `admin_edit_page` view.

- [ ] **Step 1: Write failing endpoint-level tests**

Add to `modules/users/tests/test_api_admin.py` inside `class TestAdminDisableEnable`:

```python
@pytest.mark.anyio
async def test_enable_nonexistent_returns_404(self, admin_client):
    resp = await admin_client.patch(f"/api/users/admin/{uuid.uuid4()}/enable")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"
```

Add to `class TestAdminSetRoles`:

```python
@pytest.mark.anyio
async def test_set_roles_nonexistent_returns_404(self, admin_client):
    resp = await admin_client.put(
        f"/api/users/admin/{uuid.uuid4()}/roles",
        json={"role_names": ["user"]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"
```

Add a new test class at the bottom of `test_api_admin.py`:

```python
class TestAdminResetPasswordLink:
    @pytest.mark.anyio
    async def test_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.post(f"/api/users/admin/{uuid.uuid4()}/reset-password-link")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "User not found"

    @pytest.mark.anyio
    async def test_returns_link(self, admin_client, users_db):
        user = await _make_user(users_db, email="linktarget@example.com")
        resp = await admin_client.post(f"/api/users/admin/{user.id}/reset-password-link")
        assert resp.status_code == 200
        body = resp.json()
        assert body["link"].startswith("http://testserver/users/reset-password?token=")
```

Add to `modules/users/tests/test_views.py` (near the existing admin-edit-page tests if present, else at the bottom):

```python
@pytest.mark.anyio
async def test_admin_edit_page_unknown_user_returns_404(admin_client):
    import uuid

    resp = await admin_client.get(
        f"/users/admin/{uuid.uuid4()}",
        follow_redirects=False,
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run the new tests — expect failures**

```bash
uv run pytest modules/users/tests/test_api_admin.py::TestAdminDisableEnable::test_enable_nonexistent_returns_404 \
  modules/users/tests/test_api_admin.py::TestAdminSetRoles::test_set_roles_nonexistent_returns_404 \
  modules/users/tests/test_api_admin.py::TestAdminResetPasswordLink \
  modules/users/tests/test_views.py::test_admin_edit_page_unknown_user_returns_404 -v
```
Expect: failures — currently the service raises an uncaught `UserNotFoundError` that bubbles to a 500.

- [ ] **Step 3: Translate in `api_admin.py`**

Import the exception at the top:

```python
from users.exceptions import UserNotFoundError
```

Wrap each service call that may raise `UserNotFoundError`. Replace in `admin_disable_user`:

```python
async def admin_disable_user(
    user_id: uuid.UUID,
    bus: EventBus = Depends(get_event_bus),
    service: UserService = Depends(get_user_service),
):
    """Disable a user account (sets is_active=False and disabled_at)."""
    try:
        user = await service.disable(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    await bus.publish(UserDisabled(user_id=user.id))
    return await service.to_list_item(user)
```

Add `from fastapi import HTTPException` to the imports at the top.

Apply the same wrap pattern to `admin_enable_user`, `admin_set_roles`, and `admin_reset_password_link`.

- [ ] **Step 4: Translate in `views.py`**

Import at top:

```python
from users.exceptions import UserNotFoundError
```

In `admin_edit_page`, replace:

```python
user_item = await service.get_list_item(uid)
if user_item is None:
    raise HTTPException(status_code=404)
```

with:

```python
try:
    user_item = await service.get_list_item(uid)
except UserNotFoundError:
    raise HTTPException(status_code=404) from None
```

(The `if user_item is None` branch is unreachable now that `get_list_item` raises, but keeping the HTTPException(404) in place via the try/except preserves the response. Remove the dead `if` check.)

- [ ] **Step 5: Run the endpoint tests — expect pass**

```bash
uv run pytest modules/users/tests/test_api_admin.py modules/users/tests/test_views.py -v
```
Expect: all pass (new tests green; existing 404 test still green).

- [ ] **Step 6: Run full users test suite**

```bash
make test-py
```
Expect: green.

- [ ] **Step 7: Lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 8: Commit (combined Task 4 + 5)**

```bash
git add modules/users/users/exceptions.py modules/users/users/service.py \
        modules/users/users/endpoints/api_admin.py modules/users/users/endpoints/views.py \
        modules/users/tests/test_service.py modules/users/tests/test_api_admin.py \
        modules/users/tests/test_views.py
git commit -m "refactor(users): raise UserNotFoundError from service; endpoints translate to 404

Moves HTTP coupling out of UserService. Service raises domain exception;
api_admin.py and views.py catch-and-translate at the boundary. Preserves
404 status codes and 'User not found' detail strings."
```

---

## Task 6: Remove `.commit()` from service methods (item 1)

**Files:**
- Modify: `modules/users/users/service.py`

Service calls `.commit()` in 4 methods; framework convention is flush-only. Relies on the per-request `after_flush` listener to auto-commit on a successful request.

Key invariants to preserve:
- Each method's return value shape (a `User` with `roles` accessible) is unchanged.
- Event publication in the calling endpoint runs **after** the service returns — if the caller raises between service return and request end, the auto-commit rolls back.

For `invite`: roles relationship must reflect freshly inserted `UserRole` rows before `to_list_item(user)` is called.

For `disable`/`enable`: only user columns change; roles relationship is untouched — already-loaded roles are still valid.

For `set_roles`: we delete and re-insert `UserRole` rows; the `User.roles` collection is stale — needs an explicit refresh.

- [ ] **Step 1: Identify the commit sites**

```bash
grep -n "await self\._db\.commit\|self\._db\.expire_all" modules/users/users/service.py
```
Expect: hits in `invite`, `disable`, `enable`, `set_roles`.

- [ ] **Step 2: Rewrite `invite`**

Replace the current block starting with `# Assign roles` through `return user, token` with:

```python
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
```

- [ ] **Step 3: Rewrite `disable`**

Replace the method body with:

```python
async def disable(self, user_id: uuid.UUID) -> User:
    user = await self._require_user(user_id)
    user.disabled_at = datetime.now(UTC)
    user.is_active = False
    await self._db.flush()
    return user
```

Note: no `expire_all` / re-fetch needed — the mutation is on already-loaded attributes of `user`, and `user.roles` is the same collection from the initial selectinload.

- [ ] **Step 4: Rewrite `enable`**

```python
async def enable(self, user_id: uuid.UUID) -> User:
    user = await self._require_user(user_id)
    user.disabled_at = None
    user.is_active = True
    await self._db.flush()
    return user
```

- [ ] **Step 5: Rewrite `set_roles`**

```python
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
```

- [ ] **Step 6: Run the full users test suite**

```bash
make test-py
```
Expect: all green. Pay special attention to:
- `test_api_admin.py::TestAdminDisableEnable` — verifies `is_active` and `disabled_at` in the response.
- `test_api_admin.py::TestAdminSetRoles` — verifies the roles list in the response.
- `test_api_admin.py::TestAdminInvite` — verifies the invited user is returned with expected shape.

If any of these fail, the flush-vs-commit change is the cause. Investigate — do not paper over with explicit commits.

- [ ] **Step 7: Run full repo test suite (smoke)**

```bash
make test
```
Expect: green. Catches any cross-module interaction.

- [ ] **Step 8: Lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 9: Commit**

```bash
git add modules/users/users/service.py
git commit -m "refactor(users): service uses flush only; framework auto-commits

Complies with CLAUDE.md convention that service code must not call
session.commit() — the per-request session auto-commits via after_flush."
```

---

## Task 7: Rename `services.py` → `state.py`, `UsersServices` → `UsersState` (item 2)

**Files:**
- Rename: `modules/users/users/services.py` → `modules/users/users/state.py`
- Modify: `modules/users/users/module.py`
- Modify: anywhere else that imports from `users.services`

- [ ] **Step 1: Find all references**

```bash
```

Use Grep:
```
pattern: users\.services|UsersServices|from users import services
```

Record every file + line that matches. Expected hits: `module.py` (import + `UsersServices()` call), possibly some tests.

- [ ] **Step 2: Rename the file**

```bash
git mv modules/users/users/services.py modules/users/users/state.py
```

- [ ] **Step 3: Rename the class inside `state.py`**

Open `modules/users/users/state.py`; rename `class UsersServices` to `class UsersState`. Update the file's docstring to refer to `UsersState`.

- [ ] **Step 4: Update imports in `module.py`**

In `modules/users/users/module.py`:
- `from users.services import UsersServices` → `from users.state import UsersState`
- `services = UsersServices(settings=UsersSettings())` → `state = UsersState(settings=UsersSettings())`
- `app.state.users = services` → `app.state.users = state`
- Any references to `services.mailer`, `services.rate_limiter`, etc. in the `on_startup` hook — **do not rename**: the LOCAL variable `services` is fine; only the TYPE and the file change. However, keeping consistency, rename the local variable to `state`:
  - `services = app.state.users` → `state = app.state.users`
  - `s = services.settings` → `s = state.settings`
  - `services.mailer = ...` → `state.mailer = ...`
  - (and similarly for `rate_limiter`, `auth_throughput_limiter`)

- [ ] **Step 5: Update any other imports**

For each grep hit from Step 1 that isn't `module.py`, update `from users.services import ...` to `from users.state import ...` and `UsersServices` → `UsersState`.

- [ ] **Step 6: Re-grep to verify nothing slipped**

Use Grep:
```
pattern: users\.services|UsersServices
```
Expected: no matches.

- [ ] **Step 7: Run full users test suite**

```bash
make test-py
```
Expect: green.

- [ ] **Step 8: Run full repo test suite**

```bash
make test
```
Expect: green.

- [ ] **Step 9: Lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 10: Commit**

```bash
git add modules/users/users/state.py modules/users/users/module.py
# plus anything else grep surfaced
git commit -m "refactor(users): rename services.py → state.py, UsersServices → UsersState

Disambiguates from service.py (holds UserService). The dataclass at
app.state.users is module state, not a 'services' collection."
```

---

## Task 8: Split `test_models.py` by model (item 6)

**Files:**
- Create: `modules/users/tests/test_user_model.py`
- Create: `modules/users/tests/test_role_model.py`
- Create: `modules/users/tests/test_user_role_model.py`
- Create: `modules/users/tests/test_access_token_model.py`
- Create: `modules/users/tests/test_constants.py`
- Delete: `modules/users/tests/test_models.py`

Current file is 299 LOC, at the cap. Split by responsibility. **Every test function keeps its current name and body** — only the containing file changes.

Mapping:
| Source tests | New file |
|---|---|
| `class TestUserTableShape` | `test_user_model.py` |
| `class TestRoleTableShape` | `test_role_model.py` |
| `class TestUserRoleTableShape` + `test_user_role_composite_pk` + `test_fk_cascade_delete_user_removes_user_role` + `test_seed_inserted_role_joins_orm_user_role` | `test_user_role_model.py` |
| `class TestUserAccessTokenTableShape` + `test_user_access_token_insert` | `test_access_token_model.py` |
| `class TestConstants` | `test_constants.py` |

The shared `column_names` helper (top of the current file) should be duplicated into each file that uses it (`test_user_model.py`, `test_role_model.py`). It's a 3-line function; DRY'ing to a helper module is overkill for this.

- [ ] **Step 1: Capture current test names**

```bash
uv run pytest modules/users/tests/test_models.py --collect-only -q > /tmp/test_models_before.txt
wc -l /tmp/test_models_before.txt
```
Record the count.

- [ ] **Step 2: Create `test_user_model.py`**

Copy the file docstring, imports, `column_names` helper, and `class TestUserTableShape` from `test_models.py`. Adjust the docstring to reflect the narrower scope.

- [ ] **Step 3: Create `test_role_model.py`**

Same approach, with `class TestRoleTableShape`.

- [ ] **Step 4: Create `test_user_role_model.py`**

Includes: `class TestUserRoleTableShape`, `test_user_role_composite_pk`, `test_fk_cascade_delete_user_removes_user_role`, `test_seed_inserted_role_joins_orm_user_role`. The seed-migration/ORM invariant test belongs here because it's about the UserRole join.

- [ ] **Step 5: Create `test_access_token_model.py`**

Includes: `class TestUserAccessTokenTableShape`, `test_user_access_token_insert`.

- [ ] **Step 6: Create `test_constants.py`**

Includes: `class TestConstants`.

- [ ] **Step 7: Delete the old file**

```bash
git rm modules/users/tests/test_models.py
```

- [ ] **Step 8: Capture new test names**

```bash
uv run pytest modules/users/tests/test_user_model.py \
              modules/users/tests/test_role_model.py \
              modules/users/tests/test_user_role_model.py \
              modules/users/tests/test_access_token_model.py \
              modules/users/tests/test_constants.py \
              --collect-only -q > /tmp/test_models_after.txt
```

- [ ] **Step 9: Diff the test names**

```bash
diff <(sort /tmp/test_models_before.txt) <(sort /tmp/test_models_after.txt)
```
Expect: **identical bodies, only file-path prefixes differ.** If any test name is missing or duplicated, stop and fix.

More precisely, compare just the test identifiers after the `::`:

```bash
awk -F'::' '{print $NF}' /tmp/test_models_before.txt | sort > /tmp/before_names.txt
awk -F'::' '{print $NF}' /tmp/test_models_after.txt | sort > /tmp/after_names.txt
diff /tmp/before_names.txt /tmp/after_names.txt
```
Expect: no diff.

- [ ] **Step 10: Run the new test files**

```bash
uv run pytest modules/users/tests/test_user_model.py \
              modules/users/tests/test_role_model.py \
              modules/users/tests/test_user_role_model.py \
              modules/users/tests/test_access_token_model.py \
              modules/users/tests/test_constants.py -v
```
Expect: all pass.

- [ ] **Step 11: Run full users test suite**

```bash
make test-py
```
Expect: green.

- [ ] **Step 12: Lint (verifies no file exceeds the cap)**

```bash
make lint
```
Expect: green.

- [ ] **Step 13: Commit**

```bash
git add modules/users/tests/test_user_model.py \
        modules/users/tests/test_role_model.py \
        modules/users/tests/test_user_role_model.py \
        modules/users/tests/test_access_token_model.py \
        modules/users/tests/test_constants.py \
        modules/users/tests/test_models.py
git commit -m "refactor(users): split test_models.py by model

Current file sat at 299 LOC (one under the cap). Split by responsibility:
user/role/user_role/access_token/constants. Every test keeps its original
name and body; only the containing file changes."
```

---

## Final verification

- [ ] **Step 1: Full repo test suite**

```bash
make test
```
Expect: green.

- [ ] **Step 2: Lint**

```bash
make lint
```
Expect: green.

- [ ] **Step 3: `make doctor`** — sanity check module diagnostics

```bash
make doctor
```
Expect: no new warnings; SM012 should not fire for users (register_settings sets `app.state.users`).

- [ ] **Step 4: Public-contract diff**

Verify no observable surface changed:

```bash
git diff main -- modules/users/users/contracts/
```
Expect: no changes (contracts module untouched).

- [ ] **Step 5: Verify invariants enforced**

```bash
```

Use Grep to confirm `service.py` is clean:
```
pattern: fastapi|HTTPException|session\.commit|_db\.commit
path: modules/users/users/service.py
```
Expect: **no matches** (service imports no fastapi symbols and calls no commit).

```
pattern: UsersServices|services\.py
path: modules/users/
```
Expect: **no matches**.

- [ ] **Step 6: Branch is ready**

At this point all 8 issues from the spec are addressed. Move to the superpowers:finishing-a-development-branch skill to decide on merge strategy.
