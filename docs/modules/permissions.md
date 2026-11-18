# permissions

The permissions module decouples role-based and per-user permission grants from the framework's in-memory `PermissionRegistry`. It owns:

- Two assignment tables (`permissions_role_permission`, `permissions_user_permission`).
- An admin UI to edit them.
- A grant source that feeds direct user grants into the framework's permission resolution.

There is one `RequiresPermission`, in `simple_module_hosting.permissions`. With this module installed it honours direct user grants as well as roles, and so does everything else that reads the resolved set: `resolved_permissions_for`, the menu filter, and the frontend's `auth.permissions`. Import the dependency directly from hosting.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Permissions` |
| `route_prefix` | `/api/permissions` |
| `view_prefix` | `/admin/permissions` |
| `depends_on` | `["Auth"]` |

Accounts come from the [user directory](/framework/user-directory), and roles
come from the [role directory](/framework/user-directory#role-directory).
`Users` is an optional ordering dependency. OIDC/Keycloak mappings expose
application role names to the editor without local role assignment controls.
No Users package or role table is required (#953).

## Routes

### API

All require authentication. Read endpoints need `permissions.view`; mutate endpoints need `permissions.manage`.

**Behaviour change (#687):** `permissions.manage` alone does not allow escalation.
Role and user updates require platform-level `permissions.manage` and refuse
added keys outside the actor's platform-level access (global roles, claims,
direct grants, other grant sources, and token scopes). Synthetic `tenant:*`
roles do not contribute to this ceiling. Updates also refuse user or role
targets with permissions beyond that ceiling, admin targets, or users whose
provider cannot report their roles. Unscoped admins are unrestricted. API
refusals return HTTP 403 with a reason in `detail`; Inertia writes redirect with
a form error. Existing role keys may be retained or removed only when the role
is within reach; unregistered submitted keys are still ignored and stored grants
for unavailable modules are preserved. See [delegated permission editing](/framework/permissions#delegated-permission-editing).

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
| `GET /admin/permissions/` | `Permissions/Browse` (role mappings and user grants) | `permissions.manage` |
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

`RequiresPermission(permission, *alternatives)` accepts one or more keys and 403s unless the request's user holds **any** of them, considering:

1. The keys assigned to any of the user's roles.
2. The keys assigned directly to the user (`permissions_user_permission`), contributed by `permissions.grants.source.direct_grant_source` via `PermissionRegistry.add_grant_source`.
3. The implicit `WILDCARD` grant. The `admin` role is synced to hold every permission key at startup, so admins pass any check.

All three are resolved once per request by `InertiaLayoutDataMiddleware` and cached on `request.state.resolved_permissions`.

Workers that start together (a fresh install, or a release that adds keys) all see the same admin grants missing. Each inserts them through the ORM in a savepoint and, if another worker got there first, reads again and inserts only what is still missing, so every startup succeeds (#732).

### Caching and propagation

The grant source runs on every authenticated request, so each application caches a user's direct grants for 30 seconds (`permissions.grants.source.GRANTS_TTL_SECONDS`). Co-hosted applications keep separate caches, and a bus invalidation clears only the cache of the app it was subscribed for, even for the same user UUID (#736). Maintenance paths with no app (`clear_grants_cache()`, account cleanup) still clear every app's cache, which only forgets. Saving a user's grants publishes `permissions.user_grants` on the `InvalidationBus` once the transaction commits. `PermissionService.set_user_permissions` owns this callback, so service callers
receive the same invalidation as endpoints (#687, #621); rollback publishes nothing.
Pass `app` to the service for cross-worker delivery. Without an app, commit clears
the local grant cache. Callers need no separate invalidation helper. A service constructed without a `request` is a trusted
in-process caller; pass the actor's request for delegated writes.
The worker that made the change sees it on the next request. Other workers see it immediately when `background_tasks` provides a Redis transport, and otherwise within the TTL.

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
| `RoleOut` | `id`, `name`, `label`, `description`. |
| `RolePermissionsOut` | A role plus its assigned permission keys. |
| `RolePermissionsUpdate` | `{ "permissions": ["orders.view", ...] }` — replaces the full set. |
| `UserOut` | `id`, `email`, `full_name`. |
| `UserPermissionsOut` | A user, `roles_known`, direct grants, and known role-inherited grants. |
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
| `user_id` | `UUID` | composite PK; provider-neutral account UUID |
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

The Access admin sidebar includes Permissions (`permissions.manage`). Local Users pages also link to the editor.

## Inertia pages

- `Permissions/Browse.tsx` — provider roles, user search and grant counts; external roles stay managed in the IdP.
- `Permissions/RoleEdit.tsx` — checkbox grid grouped by `PermissionGroup`; submits the full set on save.
- `Permissions/UserEdit.tsx` — same grid, with badges showing which permissions are inherited from roles vs granted directly.

## Locales

Top-level keys in `permissions/locales/en.json`: `browse`, `table`, `edit` (role editor), `user_edit` (user editor), `toasts`, `errors`.
