# simple_module_permissions

Role-based access control (RBAC) for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users get roles, roles carry permissions, and route handlers declare required permissions at the decorator or dependency layer.

Pre-wired into any app scaffolded with `smpy new`.

## Install

```bash
pip install simple_module_permissions
```

## What it provides

- `Role` and `Permission` SQLModel tables, seeded from module-registered defaults.
- Direct user-level grants feed the framework's permission resolution through a grant source, so `simple_module_hosting.auth.permissions.RequiresPermission` honours them.
- Provider-neutral admin UI for role permission mappings and direct user grants at `/admin/permissions/`; role and user editors live at `/admin/permissions/roles/{id}/edit` and `/admin/permissions/users/{id}/edit`.
- `register_permissions(self, registry)` hook — every module declares its permission strings at boot via `registry.add_group(...)`; the registry dedupes and persists them.

## Usage

Declare permissions at module boot:

```python
# modules/orders/orders/module.py
from simple_module_core.access.permissions import PermissionRegistry


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="orders")

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group("Orders", ["orders.read", "orders.write"])
```

Guard a route:

```python
from fastapi import APIRouter, Depends
from simple_module_hosting.auth.permissions import RequiresPermission

router = APIRouter()


@router.get("/orders", dependencies=[Depends(RequiresPermission("orders.read"))])
async def list_orders(): ...
```

Admin flow: open `/admin/permissions/` to edit role permission mappings or direct user grants. Users manages local role membership; OIDC and Keycloak manage membership in the identity provider.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting` (Users is optional)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
