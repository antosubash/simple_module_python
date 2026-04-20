# Users Module — Quality Pass (Sub-project 1 of 4)

**Date:** 2026-04-17
**Status:** Design approved, pending implementation plan.
**Scope:** Behavior-preserving refactor of the `users` module.

This is the first of four sub-projects improving the user-management module. The remaining three (Admin UX, Self-service, Security features) get their own specs after this ships.

## Goal

Pay down accumulated quality debt in `modules/users/users` without changing any externally observable behavior. When this lands:

- JSON request/response shapes are unchanged.
- HTTP status codes and `detail` error strings are unchanged.
- Inertia page props and page names are unchanged.
- Event publication timing (UserInvited, UserDisabled, RoleAssigned) is unchanged.
- Mailer side-effects are unchanged.

Anything a consumer could observe remains identical. Only the module's internal structure improves.

## Non-goals

- No new user-facing features (those belong to sub-projects 2–4).
- No database migrations.
- No dependency additions.
- No changes to `framework/` code.

## Problems (8)

Established during brainstorming against the current state of `modules/users/users/`:

| # | Problem | Evidence |
|---|---|---|
| 1 | Service layer calls `session.commit()`, violating the framework convention that only the per-request session lifecycle commits | `modules/users/users/service.py` lines 117, 130, 144, 177 |
| 2 | `service.py` (holds `UserService`) vs `services.py` (holds `UsersServices` app-state dataclass) — one-letter filenames that invite mis-imports | Two sibling files, class names `UserService` / `UsersServices` |
| 3 | `UserService` raises `HTTPException` directly, coupling the service layer to the HTTP transport | `modules/users/users/service.py` — 4 lazy `from fastapi import HTTPException` imports |
| 4 | The same `_get_user_with_roles → None → raise HTTPException(404)` block is duplicated across 4 methods | `service.py:124–127, 138–141, 158–161, 190–192` |
| 5 | Stale comments referring to superseded context | `module.py:1` ("replaces Keycloak"); `endpoints/api.py:102` ("once wired in Task 8") |
| 6 | `test_models.py` sits at 299 LOC, one line under the 300-line cap | `modules/users/tests/test_models.py` |
| 7 | Roles-payload boilerplate duplicated in three admin view handlers | `endpoints/views.py` — `admin_index`, `admin_invite_page`, `admin_edit_page` |
| 8 | Function-scope imports for non-optional dependencies | `bootstrap.py` — `PasswordHelper` imported twice inside function bodies |

## Proposed fixes

### 1. Remove `.commit()` from the service layer

**Before:** `UserService.invite`, `.disable`, `.enable`, `.set_roles` each call `await self._db.commit()` mid-method, then re-fetch the user with roles loaded.

**After:** service uses `await self._db.flush()` where it needs DB-assigned values or needs the session to emit pending INSERTs/UPDATEs. The per-request `get_db` dependency auto-commits at end of request (via the existing `after_flush` listener).

For methods that need to return the mutated user with roles eager-loaded: replace the `commit + expire_all + re-select` dance with `flush + refresh(user, attribute_names=["roles"])`.

**Observable impact:** none. If the request raises after the service returns, the auto-commit path rolls back — identical to today's behavior if an endpoint raised between the service's `commit()` and the request end.

### 2. Rename `services.py` → `state.py`; `UsersServices` → `UsersState`

The dataclass at `app.state.users` holds settings, mailer, rate limiters, and the roles cache. It is module state, not "services." Renaming disambiguates from `service.py` (which holds `UserService`, an admin-ops service).

Files touched:
- `modules/users/users/services.py` → `modules/users/users/state.py`
- Class `UsersServices` → `UsersState`
- Imports updated in `module.py`, `deps.py`, tests.

### 3. Introduce `UserNotFoundError`; move HTTP translation to endpoints

New file `modules/users/users/exceptions.py` defining:

```python
class UserNotFoundError(Exception):
    def __init__(self, user_id): ...
```

Kept module-internal (not in `contracts/`) because no other module catches it today. If that changes, it can be promoted later.

Endpoints at the boundary (`api_admin.py`, `views.py`, `api.py`) import the exception and translate:

```python
try:
    user = await service.disable(user_id)
except UserNotFoundError:
    raise HTTPException(status_code=404, detail="User not found") from None
```

The `detail` string matches what `service.py` currently passes to `HTTPException`, so public responses are bit-identical.

### 4. Collapse duplicated not-found blocks

Private helper in `UserService`:

```python
async def _require_user(self, user_id: uuid.UUID) -> User:
    user = await self._get_user_with_roles(user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user
```

`disable`, `enable`, `set_roles`, `generate_reset_link`, `get_list_item` all call `_require_user` instead of duplicating the check.

### 5. Delete stale comments

- `modules/users/users/module.py` line 1 docstring — rewrite to describe the current role (local user management, auth backing).
- `modules/users/users/endpoints/api.py` — delete the "once wired in Task 8" comment; AuthMiddleware is already wired.
- Any other stale plan-task references found during implementation.

### 6. Split `test_models.py`

299 LOC, one line from the cap. Split by model under test, keeping the existing test names so coverage is unambiguously preserved:

- `test_user_model.py` — `User` table tests
- `test_role_model.py` — `Role` table tests
- `test_user_role_model.py` — `UserRole` tests
- (`test_access_token_model.py` if the file covers it — confirmed during implementation)

Rule: every test function keeps its current name and body. Only the containing file changes.

### 7. Roles-payload helper in `views.py`

```python
async def _roles_payload(app) -> list[dict[str, str]]:
    return [{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]
```

Replaces three inline list-comprehensions. No public-contract change.

### 8. Promote function-scope imports

`bootstrap.py` — move `from fastapi_users.password import PasswordHelper` to module top. It is not an optional dependency and is imported on every call today.

The lazy `HTTPException` imports in `service.py` disappear as a side-effect of fix #3.

Any remaining lazy import stays lazy (e.g., anything inside lifecycle hooks that genuinely needs the app context).

## Architecture: boundary rules enforced after this

- `service.py` imports no `fastapi` symbols. It returns domain objects or raises domain exceptions.
- `service.py` never calls `session.commit()`.
- `api.py`, `api_admin.py`, `views.py` are the translation layer: they catch `UserNotFoundError` and raise `HTTPException(404)`. They are the only layer that knows about HTTP.
- `state.py` holds module singletons; `service.py` holds admin operations. No file named `services.py`.

A future `make doctor` check could enforce the "no `fastapi.HTTPException` in `service.py`" rule, but that is out of scope for this spec.

## Testing (TDD)

Every change is made via red-green-refactor.

### Rules

- For each new unit (the exception type, the `_require_user` helper, the `_roles_payload` helper, the `UsersState` rename), a failing test is written and observed to fail before the implementation lands.
- For each behavior-preserving refactor (items 1, 5, 7, 8), the existing tests are the safety net; they must continue to pass unchanged. No implementation edit lands until the full users-module test suite is green.
- Mocks are avoided. The module already has real DB fixtures (`db_session`, `authenticated_client`); those are used.

### New tests (red-first)

1. `UserService.disable|enable|set_roles|generate_reset_link|get_list_item` with an unknown UUID raises `UserNotFoundError` (not `HTTPException`). One parameterised test in a new `test_service.py`, or added to `test_user_manager.py` if co-location makes more sense.
2. `api_admin` endpoints (`PATCH /admin/{id}/disable`, `PATCH /admin/{id}/enable`, `PUT /admin/{id}/roles`, `POST /admin/{id}/reset-password-link`) return 404 with `detail="User not found"` when the UUID doesn't exist — covers the endpoint-level translation. Added to `test_api_admin.py`.
3. `views.admin_edit_page` with an unknown UUID returns 404 — covers the view-level translation. Added to `test_views.py`.
4. `_roles_payload(app)` returns the correct shape and stays in sync with `get_roles_cache`. One test in `test_views.py` or a new `test_views_helpers.py`.

### Regression guard (green)

After each step:
- `make test-py` on `modules/users/tests/` — must pass.
- `make lint` — must pass (300-line cap, ruff, ty).

### Coverage preservation (item 6 test split)

Before splitting `test_models.py`, capture the list of test names. After splitting, the same set of names must exist across the new files. Diff is run manually during implementation.

## Build sequence

Each step is independently shippable; after each one, `make test` and `make lint` must be green before the next step begins. TDD discipline applies throughout.

1. **Cleanup (items 5, 7, 8).** Local edits, no behavior risk.
   - Step 1a: stale comments (item 5).
   - Step 1b: `_roles_payload` helper — red test first (item 7).
   - Step 1c: promote imports (item 8).
2. **Domain exception (items 3 + 4).**
   - Step 2a: write red tests asserting `UserNotFoundError` from the 5 service methods.
   - Step 2b: add `exceptions.py`, `_require_user`, refactor service. Verify green.
   - Step 2c: write red tests at the endpoint layer asserting 404 + detail.
   - Step 2d: endpoints catch + translate. Verify green.
3. **Commit removal (item 1).** Rely on the existing service test suite — behavior must be unchanged.
   - Step 3a: replace `.commit()` with `.flush()` + `refresh`.
   - Step 3b: run full users test suite; investigate any change.
4. **Rename (item 2).**
   - Step 4a: move `services.py` → `state.py`, rename class.
   - Step 4b: update all imports. Run full repo test suite.
5. **Test split (item 6).**
   - Step 5a: capture current test names.
   - Step 5b: split file. Confirm test count and names match.

## Risks

- **Auto-commit assumption (item 1).** Today the service's explicit `commit()` persists mutations synchronously; after this change they persist when the request handler returns cleanly. If a subsequent endpoint-level check raises between service return and request end, the mutation is rolled back. This matches the framework convention and is what other modules rely on. The test suite covers the mutation endpoints end-to-end, so this is low-risk.
- **Rename surface (item 2).** Grep-based find-replace; `make lint` + full test suite catches misses.
- **Nothing else is risky.**

## Out of scope (deferred to sub-projects 2–4)

- Admin UX: bulk actions, filtering, sorting, user detail page, activity log.
- Self-service: password change, email change, API tokens, delete-my-account.
- Security: 2FA, active session management, password strength meter, lockout visibility.

## Acceptance criteria

- All 8 problems addressed per the mapping above.
- Full repo test suite passes.
- `make lint` passes.
- No public-contract diff: compare before/after for `modules/users/users/contracts/schemas.py`, status codes, response bodies in `test_api_admin.py` / `test_api_auth.py` / `test_views.py`.
- `service.py` contains no `fastapi` import and no `session.commit()` call.
- File `services.py` no longer exists; `state.py` exists with `UsersState`.
