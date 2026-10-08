# permissions

The permissions module decouples role-based and per-user permission grants from the framework's in-memory `PermissionRegistry`. It owns:

- Two assignment tables (`permissions_role_permission`, `permissions_user_permission`).
- An admin UI to edit them.
- A grant source that feeds direct user grants into the framework's permission resolution.

There is one `RequiresPermission`, in `simple_module_hosting.permissions`. With this module installed it honours direct user grants as well as roles, and so does everything else that reads the resolved set: `resolved_permissions_for`, the menu filter, and the frontend's `auth.permissions`. `permissions.deps.RequiresPermission` is the same class, kept so existing imports still work. Before GH #337 they were separate classes, and a direct grant took effect only on routes that imported the `permissions.deps` one.

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
from simple_module_hosting.permissions import RequiresPermission

router = APIRouter()


@router.delete(
    "/orders/{order_id}",
    dependencies=[Depends(RequiresPermission("orders.delete"))],
)
async def delete_order(order_id: int) -> None: ...
```

`RequiresPermission(permission)` takes a **single** permission key and 403s unless the request's user holds it, considering:

1. The keys assigned to any of the user's roles.
2. The keys assigned directly to the user (`permissions_user_permission`), contributed by `permissions.grants.direct_grant_source` via `PermissionRegistry.add_grant_source`.
3. The implicit `WILDCARD` grant. The `admin` role is synced to hold every permission key at startup, so admins pass any check.

All three are resolved once per request by `InertiaLayoutDataMiddleware` and cached on `request.state.resolved_permissions`. `auth.deps.require_permission(*keys)` reads the same set, with any-of semantics.

### Caching and propagation

The grant source runs on every authenticated request, so each process caches a user's direct grants for 30 seconds (`permissions.grants.GRANTS_TTL_SECONDS`). Saving a user's grants publishes `permissions.user_grants` on the `InvalidationBus` once the transaction commits. The worker that made the change sees it on the next request. Other workers see it immediately when `background_tasks` provides a Redis transport, and otherwise within the TTL.

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
