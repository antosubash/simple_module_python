# Permissions

Permissions are **strings** owned by modules and enforced at endpoint boundaries. The framework doesn't know about specific permission strings — each module declares its own and attaches them to roles via the admin UI.

## Declaring permissions

Inside a module's `register_permissions(registry)`:

```python
from simple_module_core.permissions import PermissionRegistry


class OrdersModule(ModuleBase):
    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Orders",
            [
                "orders.view",
                "orders.create",
                "orders.edit",
                "orders.delete",
                "orders.export",
            ],
        )
```

The group name (`"Orders"`) is the display label in the role editor. Permission strings conventionally use `<module>.<verb>` lowercase.

## Enforcing at endpoints

Use the `RequiresPermission` dependency from `simple_module_hosting.permissions`:

```python
from fastapi import APIRouter, Depends
from simple_module_hosting.permissions import RequiresPermission

router = APIRouter()

@router.post(
    "",
    status_code=201,
    dependencies=[Depends(RequiresPermission("orders.create"))],
)
async def create_order(...): ...

@router.get(
    "/export",
    dependencies=[
        Depends(RequiresPermission("orders.view")),
        Depends(RequiresPermission("orders.export")),
    ],
)
async def export_orders(...): ...
```

`RequiresPermission` raises `HTTPException(403)` if the current user lacks the permission. Unauthenticated requests return 401 — `AuthMiddleware` runs earlier and attaches `request.state.user` (a `UserContext`) plus the resolved permission set on `request.state.resolved_permissions`.

## Roles

Roles are named collections of permissions stored in the `users_role` table (owned by the `users` module). The mapping from role to permissions lives in `DEFAULT_ROLE_PERMISSIONS` (framework default) + per-role overrides in the DB.

```python
# simple_module_hosting.permissions
DEFAULT_ROLE_PERMISSIONS = {
    "admin": ["*"],
}
```

Host apps customize this by:

1. Editing roles in the admin UI at `/admin/users/` (Roles tab).
2. Or seeding via code during `on_startup` in a custom host-level module.

The framework ships only `admin: ["*"]`. The wildcard grants every declared permission.

## Runtime permission sources

`register_permissions` runs before the database is open, so it cannot declare permissions for resources admins create later (per-record-type keys such as `records.product.edit`). Register a **source** instead:

```python
def register_permissions(self, registry: PermissionRegistry) -> None:
    registry.add_source("records", lambda: [("records.product.edit", "Edit products")])
```

The provider is **sync** and must read a module-maintained in-memory cache, because the registry is consulted on every request. It returns permission keys or `(key, label)` pairs. Its output is cached by the registry; call `registry.invalidate_source("records")` when the underlying resources change. Source permissions appear in `all_permissions`, in the role editor under the source's group name (labels ship in `PermissionGroupOut.labels`), in admin's implicit all-permissions, and are enforced by `RequiresPermission`. They are grantable and persisted like any other key. A source that raises is logged and contributes nothing.

## User resolution

For each request, `AuthMiddleware` resolves the authenticated user onto `request.state.user` as a `UserContext` (from `auth.contracts.schemas`):

```python
@dataclass
class UserContext:
    id: str
    email: str
    name: str
    roles: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    permissions: list[str] = field(default_factory=list)
```

The active auth provider (the `users` or `keycloak` module) owns extraction from the session cookie / bearer token. `InertiaLayoutDataMiddleware` then expands roles into a permission set (cached on `request.state.resolved_permissions`) and serializes `auth.user`, `auth.isAuthenticated`, `auth.permissions` into the Inertia shared props. Permissions are derived mostly from roles via the `PermissionRegistry.role_map`. `UserContext.permissions` adds keys the principal carries itself — a token scope or IdP claim a provider or principal resolver maps in. `resolve_principal_permissions` (and so `RequiresPermission`, `require_permission` and `auth.permissions`) merges them into the role-derived set, **dropping `*`**: like a grant source, a claim can never confer the wildcard; admin comes from roles only. They are written into the session cookie with `roles` and frozen there until the next sign-in, so anything an admin must be able to revoke belongs in a grant source, not here. `UserContext.has_permission(key)` is an exact-match check against that list alone.

## Scoped principals (API tokens) and ungated routes

A principal with `UserContext.scopes` set — an [`api_tokens`](/modules/api_tokens)
personal access token or service key — has its permission set capped at those
scopes. Because the cap can only constrain a route that asks for a permission,
`simple_module_hosting.token_guard` (installed by `create_app` as an app-wide
dependency) applies a fail-closed rule to every route:

- a route whose dependency tree contains `RequiresPermission(...)` or
  `auth.deps.require_permission(...)` admits tokens — the gate decides;
- a page (a module view router, or any route depending on `InertiaDep`)
  refuses tokens with 403, gated or not;
- `Depends(TokenAllowed())` from `simple_module_hosting.token_guard` admits
  tokens explicitly, without a permission;
- `Depends(Authenticated())` marks "any signed-in user may call this" (401 with
  no principal). It satisfies diagnostic `SM031` and the OpenAPI export but is
  **not** a token opt-in: alone, a token is still refused; add `TokenAllowed()`
  to admit one too;
- every other route refuses tokens with 403 — except a public route, where the
  token's principal is dropped and the request runs anonymously (no user, no
  permissions, and the tenant an anonymous request would resolve to).

So **gate a route with a permission dependency if API tokens should reach it**;
a permission checked inline in the handler does not count. A gate passed as
`include_router(..., dependencies=[...])` counts: the guard reads the route as
FastAPI runs it (`scope["fastapi"]["effective_route_context"]`), include-level
dependencies included. Should a future FastAPI stop recording that context,
such a route falls back to failing closed (tokens refused), and a page still
refuses tokens through `page_route` itself. Sessions and a
provider's own bearer tokens (`auth_kind == "bearer"`) are unscoped and
unaffected. A custom gate dependency can mark itself with
`mark_token_gate(fn, GATE_PERMISSION)`.

## Role shorthand for menus

`MenuItem.roles` hides an item from users who hold none of the listed roles (an empty list = visible to all authenticated users); `requires_auth` (default `True`) hides it from anonymous visitors. Filtering happens in `MenuRegistry.get_for_user`, called by `InertiaLayoutDataMiddleware` *before* the menu reaches the client — so the client never sees menu items it can't use.

```python
registry.add(
    MenuItem(
        section=MenuSection.SIDEBAR,
        label="orders.menu.orders",
        url="/orders",
        roles=["admin"],
    )
)
```

Menu visibility is **role**-based (`MenuItem` has no `required_permission` field) — see `simple_module_core.menu`. Enforce the actual permission on the endpoint with `RequiresPermission`.

## Client-side checks

The Inertia shared props include `auth.permissions`. Use them for UI affordances (hide/disable buttons), not for security:

```tsx
import { usePermissions } from "@simple-module-py/ui/hooks/use-permissions";

export default function OrdersToolbar() {
  const { can } = usePermissions();
  return (
    <div>
      {can("orders.create") && (
        <Button>Create order</Button>
      )}
    </div>
  );
}
```

**Security is enforced server-side.** A client-side check only hides the button; `RequiresPermission` on the POST endpoint prevents the actual creation.

## Testing with permissions

The `authenticated_client` fixture from the `simple_module_test` plugin seeds an admin user (who has `*`). For tests that need a less-privileged user, build one from the `users` module fixtures or flip the principal temporarily:

```python
@pytest.mark.asyncio
async def test_create_requires_permission(client, db_session):
    # Create a user without `orders.create` (e.g. via the users
    # registration flow or by inserting a users.models.User row directly —
    # users.bootstrap only ships create_admin).
    ...
    # Sign in via the local-auth API to get the session cookie.
    r = await client.post("/api/users/auth/login", data={"username": "u@e.com", "password": "x"})
    assert r.status_code in (200, 204)

    r = await client.post("/api/orders", json={...})
    assert r.status_code == 403
```

## Conventions

- **Namespace with the module name.** `orders.create`, not `create_order`.
- **Use `<module>.<verb>` form.** Nouns like `orders.admin` are fine for broad grants.
- **Don't inline string checks.** `if "orders.create" in principal.permissions: ...` scattered through code is hard to audit. Use `RequiresPermission` or refactor into a dependency. When the thing to gate is part of a *response* rather than a route — a column, a label, a card — read the caller's grants with `resolved_permissions_for(request)` and test them with `simple_module_core.permissions.grants`, which is where the wildcard rule lives. A hand-rolled `in` check forgets that `admin` holds `*` and no named permission at all.
- **Don't use roles in business logic.** Check permissions, not `user.roles`. Roles are an admin concept; permissions are the enforcement boundary.
