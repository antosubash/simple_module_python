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

1. Editing roles in the admin UI at `/settings/permissions`.
2. Or seeding via code during `on_startup` in a custom host-level module.

The framework ships only `admin: ["*"]`. The wildcard grants every declared permission.

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
```

The active auth provider (the `users` or `keycloak` module) owns extraction from the session cookie / bearer token. `InertiaLayoutDataMiddleware` then expands roles into a permission set (cached on `request.state.resolved_permissions`) and serializes `auth.user`, `auth.isAuthenticated`, `auth.permissions` into the Inertia shared props. `UserContext` carries roles, not permissions — permissions are derived from the `PermissionRegistry.role_map`.

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
- **Don't inline string checks.** `if "orders.create" in principal.permissions: ...` scattered through code is hard to audit. Use `RequiresPermission` or refactor into a dependency.
- **Don't use roles in business logic.** Check permissions, not `user.roles`. Roles are an admin concept; permissions are the enforcement boundary.
