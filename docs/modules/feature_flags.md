# feature_flags

Runtime feature toggles. Modules register named flags with a default value; an admin can override them per-system or per-tenant from the UI; service code asks the in-memory registry whether a flag is on at request time. Resolution precedence: **tenant override → system override → registered default**.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `FeatureFlags` |
| `route_prefix` | `/api/feature_flags` |
| `view_prefix` | `/feature_flags` |
| `depends_on` | _(none)_ |

## Registering a flag

Anywhere a module has access to `app.state.sm.feature_flags` (typically inside `register_feature_flags`):

```python
from simple_module_core.feature_flags import FeatureFlag


class OrdersModule(ModuleBase):
    def register_feature_flags(self, registry):
        registry.register(
            FeatureFlag(
                name="orders.beta_checkout",
                description="Enable the new checkout flow",
                default_enabled=False,
            )
        )
```

Once registered, the flag shows up at `/feature_flags` in the admin UI. Unregistered names return 404 from the override endpoints — flags are explicit, not free-form keys.

## Reading a flag at request time

```python
from feature_flags.deps import FeatureFlagRegistryDep


@router.post("/checkout")
async def checkout(
    body: CheckoutRequest,
    flags: FeatureFlagRegistryDep,
    user: CurrentUser,
) -> ...:
    if flags.is_enabled("orders.beta_checkout", tenant_id=user.tenant_id):
        return await new_checkout(body, user)
    return await legacy_checkout(body, user)
```

`is_enabled(name, tenant_id=None)` resolves precedence and returns a `bool`. The registry is in-memory and hydrated at boot from the `feature_flags_override` table — no DB round-trip per call.

## Routes

### API

All require authentication. Read endpoints need `feature_flags.view`; write endpoints need `feature_flags.manage`.

| Method + path | Body / response | Permission |
|---|---|---|
| `GET /api/feature_flags/` | → `list[FeatureFlagView]` | `feature_flags.view` |
| `GET /api/feature_flags/{name}` | → `FeatureFlagView` | `feature_flags.view` |
| `PUT /api/feature_flags/{name}` | `ToggleRequest` → `FeatureFlagView` | `feature_flags.manage` |
| `DELETE /api/feature_flags/{name}` | → `204` (clear system override) | `feature_flags.manage` |
| `GET /api/feature_flags/tenant/{tenant_id}` | → `list[FeatureFlagView]` | `feature_flags.view` |
| `PUT /api/feature_flags/tenant/{tenant_id}/{name}` | `ToggleRequest` → `FeatureFlagView` | `feature_flags.manage` |
| `DELETE /api/feature_flags/tenant/{tenant_id}/{name}` | → `204` | `feature_flags.manage` |

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /feature_flags/` | `FeatureFlags/Browse` (optional `?tenant_id=...`) | `feature_flags.view` |
| `POST /feature_flags/{name}/toggle` | _redirect_ | `feature_flags.manage` |
| `POST /feature_flags/{name}/clear` | _redirect_ | `feature_flags.manage` |

## Public contracts

```python
from feature_flags.contracts.schemas import FeatureFlagView, ToggleRequest
```

| Class | Purpose |
|---|---|
| `FeatureFlagView` | What the API + admin UI returns: `name`, `description`, `default_enabled`, `enabled` (resolved), `overridden` (does *this* scope have an override?), `system_enabled` (only for tenant scope). |
| `FeatureFlagOverrideOut` | The persisted override row. |
| `ToggleRequest` | `{ "enabled": bool }`. |

## Models

`FeatureFlagOverride` (table `feature_flags_override`)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` | PK |
| `scope` | `str(10)` | `"system"` or `"tenant"` |
| `scope_id` | `str(64)` | `""` for system, the tenant id otherwise |
| `name` | `str(200)` | flag name |
| `enabled` | `bool` | the override value |
| `created_at` / `updated_at` | `datetime` | from `AuditMixin` |

Unique constraint on `(scope, scope_id, name)`. The `scope_id=""` (instead of `NULL`) sidesteps PostgreSQL's "NULLs are distinct in UNIQUE indexes" rule.

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `feature_flags.view` | admin | read flags + overrides |
| `feature_flags.manage` | admin | create / update / delete overrides |

## Menu

| Label | URL | Icon | Section | Group | Order |
|---|---|---|---|---|---|
| `Feature Flags` | `/feature_flags` | `flag` | `SIDEBAR` | `Administration` | `110` |

## Inertia pages

- `FeatureFlags/Browse.tsx` — single browse page with a system/tenant scope switcher, table of all registered flags, and toggle / clear-override actions.

## Locales

Top-level keys in `feature_flags/locales/en.json`:

- `browse` — page strings (title, description, empty state, count plurals, scope switcher).
- `table` — column headers and badges (`enabled`, `disabled`, `overridden`, `following_default`, `following_system`, `system_value`, `clear_override`).
- `toasts` — notifications (`enabled`, `disabled`, `cleared`, `toggle_failed`).

## Notes

- The `FeatureFlagService` keeps the in-memory registry in sync after every DB mutation, so `is_enabled()` is always cheap.
- Tenant-scope endpoints use a non-empty `scope_id`; the system scope uses `""`. Don't pass `None` — the unique index treats `NULL` as distinct on Postgres and you'll end up with duplicate rows.
- The `Browse` page lists tenants that have any override attached, so you can jump from system view → a tenant view that actually has overrides without typing IDs.
