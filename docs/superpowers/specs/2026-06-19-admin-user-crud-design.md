# Admin user CRUD — create, edit, delete from the admin page

**Date:** 2026-06-19
**Module:** `users`
**Status:** Proposed

## Problem

The admin Users page (`/users/admin`) can only *invite* users (email a one-time
link so the recipient sets their own password). Admins cannot create a user
directly, edit a user's email or name, or delete a user. The goal is for an
admin to perform the full set of account-management operations from the UI.

## Scope

Add three operations, exposed under the existing `users.manage` permission:

1. **Create user** — admin enters email, full name, password, and roles. The
   user is created **active and verified** and can log in immediately. No email
   is sent; the admin shares credentials out-of-band. (Invite stays as-is for
   the email-link flow.)
2. **Edit details** — admin can change a user's **email** and **full name**.
3. **Delete user** — hard-delete a user account, with a confirmation step and a
   guard preventing an admin from deleting their own account.

Already present and unchanged: list/search/filter/sort, invite, disable/enable,
mark-verified, set-roles, copy-reset-link, manage-permissions.

### Out of scope (noted so it's a deliberate choice, not an omission)

- **Directly setting a password on an existing user.** The existing
  "copy reset link" action already covers admin-driven password changes; adding
  a second path is redundant. Create sets an initial password; edits to an
  existing account's password go through the reset link.
- **Last-admin lockout protection.** Disable already lacks this guard, so adding
  it only for delete would be inconsistent. Self-delete is guarded (the common
  footgun); broader lockout protection is a separate concern.
- Changing email does **not** reset verification status. The admin is trusted;
  they can toggle verification separately if needed.

## Architecture

No new module, no new tables, no migration. This is additive surface on the
existing `users` admin slice:

```
modules/users/users/
├── admin/
│   ├── api.py          # + POST "", PATCH "/{id}", DELETE "/{id}"
│   ├── views.py        # + GET "/admin/create" (Inertia page route)
│   ├── queries.py      # NEW — read/query methods (split from service.py)
│   └── service.py      # write/command methods + NEW create/update/delete
├── contracts/
│   ├── schemas.py      # + UserAdminCreate, UserDetailsUpdate
│   └── events.py       # + UserCreated, UserDeleted
└── pages/Users/
    ├── Create.tsx      # NEW — create-user form
    ├── Index.tsx       # + "Create user" button next to "Invite member"
    ├── Edit.tsx        # + wires DetailsCard + DangerZone
    └── components/
        ├── DetailsCard.tsx  # NEW — edit email + full name
        └── DangerZone.tsx   # NEW — delete with confirm dialog
```

### Why split `service.py`

`admin/service.py` is at 272 / 300 lines. The three new methods would push it
over the CI line cap. Split by responsibility:

- `admin/queries.py` — `class _UserServiceBase`: `__init__`, `_resolve_roles`,
  `to_list_item`, `_get_user_with_roles`, `_require_user`, `list_users`,
  `count_user_states`, `list_roles`, `get_with_roles`, `get_list_item`.
- `admin/service.py` — `class UserService(_UserServiceBase)`: the write/command
  methods (`invite`, `disable`, `enable`, `mark_verified`, `set_roles`,
  `generate_reset_link`) plus the three new ones below.

`UserService` keeps its name and import path (`from users.admin.service import
UserService`), so `get_user_service` and every existing caller and test are
unchanged.

## Components

### 1. Schemas (`contracts/schemas.py`)

```python
class UserAdminCreate(SQLModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_names: list[str] = []

class UserDetailsUpdate(SQLModel):
    email: EmailStr
    full_name: str | None = None
```

### 2. Events (`contracts/events.py`)

```python
@dataclass
class UserCreated(Event):
    user_id: uuid.UUID
    email: str
    created_by: str | None

@dataclass
class UserDeleted(Event):
    user_id: uuid.UUID
```

### 3. Service methods (`admin/service.py`)

**`create_user(email, password, full_name, role_names, *, created_by) -> User`**
- Build `UserCreate(email, password, full_name, is_active=True,
  is_verified=True, is_superuser=False)` and call
  `self._manager.create(user_create, safe=False)`. This runs the password policy
  (`validate_password`) and email-uniqueness check for free, and — because
  `is_verified=True` — does **not** trigger a verification email.
- Assign roles exactly as `invite` does (resolve names → insert `UserRole` rows
  with `assigned_by=created_by`, flush, refresh `roles`).
- Return the user. (No mailer call.)

**`update_details(user_id, email, full_name) -> User`**
- `_require_user(user_id)`.
- If `email` differs (case-insensitive) from the current email, check no other
  user owns it: `select(User).where(func.lower(User.email) == email.lower(),
  User.id != user_id)`. If found, raise `EmailAlreadyExistsError` (new, in
  `exceptions.py`).
- Update `email` and `full_name`, flush, return user.

**`delete_user(user_id) -> None`**
- `_require_user(user_id)` (404 if missing).
- Explicitly delete dependent rows so behavior is identical on Postgres and
  SQLite (SQLite FK cascade depends on a pragma; don't rely on it):
  `delete(UserRole)`, `delete(UserAccessToken)`, `delete(OAuthAccount)`,
  `delete(RefreshToken)` all `where(... .user_id == user_id)`.
- Then `await self._db.delete(user)` and flush.

### 4. API endpoints (`admin/api.py`, all under `users.manage`)

| Method & path | Handler | Behavior |
|---|---|---|
| `POST /api/users/admin` | `admin_create_user` | Create. `UserAlreadyExists` → 409; `InvalidPasswordException` → 400 (detail = reason). On success publish `UserCreated`, return `UserListItem` (201). |
| `PATCH /api/users/admin/{id}` | `admin_update_user` | Edit details. `UserNotFoundError` → 404; `EmailAlreadyExistsError` → 409. Returns `UserListItem`. |
| `DELETE /api/users/admin/{id}` | `admin_delete_user` | Delete. If `id == request.state.user.id` → 400 "You cannot delete your own account." `UserNotFoundError` → 404. On success publish `UserDeleted`, return 204. |

Route note: `POST ""` and `PATCH "/{id}"` / `DELETE "/{id}"` don't collide with
the existing `/{id}/disable` etc. The new view route `GET /admin/create` must be
declared **before** `GET /admin/{user_id}` (FastAPI matches in order), same as
the existing `/admin/invite`.

### 5. View route (`admin/views.py`)

`GET /admin/create` renders `Users/Users/Create` with `{"roles":
await _roles_payload(request.app)}` — mirrors `admin_invite_page`.

### 6. Frontend

- **`Create.tsx`** — modeled on `Invite.tsx`: email, full name, **password**
  (required; helper text notes the ≥8-char rule), and role chips. Submits
  `POST /api/users/admin`; on success toast + `router.visit('/users/admin')`.
  Surfaces the server `detail` string on 400/409 (weak password / email taken).
- **`Index.tsx`** — add a primary **"Create user"** button (`Link` to
  `/users/admin/create`) alongside the existing outline **"Invite member"**.
- **`DetailsCard.tsx`** — email + full-name inputs with a Save button;
  `PATCH /api/users/admin/{id}`; toast on success, shows server `detail` on 409.
- **`DangerZone.tsx`** — "Delete user" button opening a confirm step
  (AlertDialog if available in the ui package, else `window.confirm`);
  `DELETE /api/users/admin/{id}`; on success toast + `router.visit('/users/admin')`.
  Not rendered for the admin's own row is handled server-side, but the button
  may also be hidden client-side when `user.id` is the current user (nice-to-have).
- **`Edit.tsx`** — render `DetailsCard` (top) and `DangerZone` (bottom), wiring
  to keep the file under the line cap.

## Data flow (create)

1. Admin submits Create form → `POST /api/users/admin` (JSON).
2. `RequiresPermission(users.manage)` gate → `admin_create_user`.
3. `service.create_user(...)` → `manager.create` (hash + policy + uniqueness) →
   role rows → flush. Per-request session auto-commits (pending writes).
4. Publish `UserCreated`. Return `UserListItem` (201).
5. Front end toasts and redirects to the list, where the new user appears.

## Error handling

- Weak password → 400, `detail` = the policy reason; shown inline on the form.
- Duplicate email (create or edit) → 409, `detail` = "A user with this email
  already exists."; shown inline.
- Missing user (edit/delete) → 404.
- Self-delete → 400 with a clear message; the delete button is also hidden for
  the current user client-side.
- All mutations require `users.manage`; unauthenticated `/api/*` → 401 (existing
  middleware behavior).

## Testing

Mirror existing `tests/test_service_admin.py`, `test_api_admin.py`,
`test_views_admin.py` patterns (`users_app`, `authenticated_client`).

- **Service** (`test_service_admin.py` additions):
  - `create_user` creates an active+verified user, hashes the password, assigns
    roles, and is rejected for a weak password / duplicate email.
  - `update_details` updates email + name; rejects an email owned by another user.
  - `delete_user` removes the user and its `UserRole` / token / oauth rows;
    raises `UserNotFoundError` for a missing id.
- **API** (`test_api_admin.py` additions):
  - `POST /admin` 201 + body; 409 on duplicate; 400 on weak password; 401/403
    without permission.
  - `PATCH /admin/{id}` 200; 409 on duplicate email; 404 missing.
  - `DELETE /admin/{id}` 204; 404 missing; **400 when deleting self**.
- **Views** (`test_views_admin.py` addition): `GET /admin/create` renders the
  `Create` page with roles in props.

## Verification

- `make test-py` (users suite green), `make lint` (Ruff/ty/Biome/tsc + 300-line
  cap all pass), `make doctor` (no new SM00x/SM01x warnings).
- Manual: create a user and log in as them; edit an email; delete a user and
  confirm they're gone; confirm self-delete is blocked.
