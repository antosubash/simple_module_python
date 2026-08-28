# permissions

The permissions module decouples role-based and per-user permission grants from the framework's in-memory `PermissionRegistry`. It owns:

- Two assignment tables (`permissions_role_permission`, `permissions_user_permission`).
- An admin UI to edit them.
- A `RequiresPermission` dependency that consults *both* roles and direct user grants.

The framework ships its own simpler `RequiresPermission` in `simple_module_hosting.permissions` that only checks roles; if you install the `permissions` module, prefer the one re-exported from `permissions.deps` because it also honours direct grants.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Permissions` |
| `route_prefix` | `/api/permissions` |
| `view_prefix` | `/admin/permissions` |
| `depends_on` | `["Auth", "Users"]` |

## Routes

### API

All require authentication. Read endpoints need `permissions.view`; mutate endpoints need `permissions.manage`.

| Method + path | Body / response | Permission |
|---|---|---|
| `GET /api/permissions/` | → `list[PermissionGroupOut]` | `permissions.view` |
| `GET /api/permissions/roles/{role_id}` | → `RolePermissionsOut` | `permissions.view` |
| `PUT /api/permissions/roles/{role_id}` | `RolePermissionsUpdate` → `RolePermissionsOut` | `permissions.manage` |
| `GET /api/permissions/users/{user_id}` | → `UserPermissionsOut` | `permissions.view` |
| `PUT /api/permissions/users/{user_id}` | `UserPermissionsUpdate` → `UserPermissionsOut` | `permissions.manage` |

### View

| Method + path | Inertia component / behaviour | Permission |
|---|---|---|
| `GET /admin/permissions/` | _redirect to_ `/admin/users/` | _login_ |
| `GET /admin/permissions/roles/{role_id}/edit` | `Permissions/RoleEdit` | `permissions.manage` |
| `PUT /admin/permissions/roles/{role_id}` | form action; redirects | `permissions.manage` |
| `GET /admin/permissions/users/{user_id}/edit` | `Permissions/UserEdit` | `permissions.manage` |
| `PUT /admin/permissions/users/{user_id}` | form action; redirects | `permissions.manage` |

## Using `RequiresPermission`

```python
from fastapi import APIRouter, Depends
from permissions.deps import RequiresPermission

router = APIRouter()


@router.delete(
    "/orders/{order_id}",
    dependencies=[Depends(RequiresPermission("orders.delete"))],
)
async def delete_order(order_id: int) -> None: ...
```

`RequiresPermission(permission)` takes a **single** permission key and 403s unless the request's user holds it, considering:

1. The keys assigned to any of the user's roles (read from the request-cached `resolved_permissions`).
2. The keys assigned directly to the user (`permissions_user_permission`).
3. The implicit `WILDCARD` grant — the `admin` role is synced to hold every permission key at startup, so admins pass any check.

For something tied to *only* role membership (no direct grants), use `auth.deps.require_permission` instead — it's a hair cheaper.

## Public contracts

```python
from permissions.contracts.schemas import (
    PermissionGroupOut,
    RoleOut,
    RolePermissionsOut,
    RolePermissionsUpdate,
    UserOut,
    UserPermissionsOut,
    UserPermissionsUpdate,
)
```

| Class | Purpose |
|---|---|
| `PermissionGroupOut` | A named group (e.g. `Orders`) with the list of permission keys it owns. Built from the framework's `PermissionRegistry`. |
| `RoleOut` | `id`, `name`, `description`. |
| `RolePermissionsOut` | A role plus its assigned permission keys. |
| `RolePermissionsUpdate` | `{ "permissions": ["orders.view", ...] }` — replaces the full set. |
| `UserOut` | `id`, `email`, `full_name`. |
| `UserPermissionsOut` | A user, the keys granted directly, and the keys inherited from roles. |
| `UserPermissionsUpdate` | `{ "permissions": [...] }` — replaces the user's *direct* grants only. |

## Models

`RolePermission` (table `permissions_role_permission`)

| Column | Type | Notes |
|---|---|---|
| `role_name` | `str` | composite PK |
| `permission_key` | `str` | composite PK; indexed for reverse lookups |
| `assigned_at` | `datetime` | |
| `assigned_by` | `str \| None` | actor email |

`UserPermission` (table `permissions_user_permission`)

| Column | Type | Notes |
|---|---|---|
| `user_id` | `UUID` | composite PK; references `users_user.id` |
| `permission_key` | `str` | composite PK |
| `assigned_at` | `datetime` | |
| `assigned_by` | `str \| None` | actor email |

The schema deliberately keys by **string permission key**, not a normalised `permissions` table. Permission keys are the source of truth (registered at boot from `register_permissions`); the rows here are just assignments. If a key disappears from the registry, its assignments become inert (no FK to break) and the admin UI flags them as orphans.

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `permissions.view` | admin | read groups, roles, user grants |
| `permissions.manage` | admin | edit role + user grants |

## Menu

_(none)_ — the editor is reachable from the [`users`](/modules/users) admin pages (each user/role row links to its permissions edit page).

## Inertia pages

- `Permissions/RoleEdit.tsx` — checkbox grid grouped by `PermissionGroup`; submits the full set on save.
- `Permissions/UserEdit.tsx` — same grid, with badges showing which permissions are inherited from roles vs granted directly.

## Locales

Top-level keys in `permissions/locales/en.json`: `browse`, `table`, `edit` (role editor), `user_edit` (user editor), `toasts`, `errors`.
