# Framework Conventions

Short reference for the invariants module authors rely on. When in doubt, read the linked source — it's the source of truth; this document exists so you don't have to reverse-engineer it.

## Module structure

```
modules/<name>/
├── pyproject.toml            # entry point: simple_module = "<name>.module:<Class>Module"
└── <name>/
    ├── __init__.py
    ├── module.py             # ModuleBase subclass with meta = ModuleMeta(...)
    ├── models.py             # SQLModel tables (optional)
    ├── service.py            # business logic
    ├── deps.py               # FastAPI dependencies
    ├── contracts/            # SQLModel DTOs (public surface)
    ├── endpoints/
    │   ├── api.py            # REST endpoints (JSON)
    │   └── views.py          # Inertia view endpoints
    └── pages/                # *.tsx — auto-discovered by Vite
```

Scaffold a fresh module with `smpy create-module <name> --dest modules/<name>` — it generates all of the above. Then run `uv add ./modules/<name>` to register it on your app.

## ModuleMeta

Every `ModuleBase` subclass **must** declare a `meta` class attribute:

```python
class OrdersModule(ModuleBase):
    meta = ModuleMeta(
        name="Orders",                    # PascalCase, unique
        route_prefix="/api/orders",       # mounted on the API router
        view_prefix="/orders",            # mounted on the view router
        depends_on=["Products"],          # strict load order
        version="1.0.0",
    )
```

- `name` is unique across the app — it's the schema name for PostgreSQL, the SQLite table prefix, the Inertia component namespace, and the diagnostic reporter name.
- `depends_on` expresses a hard ordering requirement; the framework topo-sorts modules and invokes lifecycle hooks in that order.
- Missing or invalid `meta` fails the boot in production (strict discovery) and logs a `SM001` warning in development.

## Discovery & entry points

Modules are registered via `[project.entry-points.simple_module]` in the module's `pyproject.toml`:

```toml
[project.entry-points.simple_module]
orders = "orders.module:OrdersModule"
```

The framework calls `discover_modules()` at app-build time. No manual wiring in the host.

In production (`SM_ENVIRONMENT != development`) discovery runs in **strict mode**: any entry-point load failure or structural error (missing `meta`, wrong base class) raises `InvalidModuleError` at boot. In development, errors are logged and the module is skipped.

## Middleware pipeline

Starlette's `add_middleware` is **LIFO** — the last middleware added is the first executed on a request. The framework installs middleware in this order inside `create_app`:

```
# Added last → first executed
CorrelationIdMiddleware
RequestLoggingMiddleware
SecurityHeadersMiddleware
SessionMiddleware
<module-registered middleware>     # each module's register_middleware()
TenantMiddleware    (if multi_tenant=True)
InertiaLayoutDataMiddleware
# Added first → last executed
```

**Execution order on a request:**

```
CorrelationId → RequestLogging → SecurityHeaders → Session
  → <modules> → Tenant → InertiaLayoutData → app
```

### Module-registered middleware ordering

When two modules at the same dependency tier both call `app.add_middleware(...)` in their `register_middleware` hook, the order is governed by topological sort and the LIFO rule: the module that sorts **later** wraps its middleware **outermost** (runs first).

If you need a specific relative order, express it with `ModuleMeta.depends_on`. Don't rely on alphabetical names.

## Settings

Framework settings live on `Settings` (`simple_module_hosting.settings`), prefix `SM_`:

```
SM_DATABASE_URL, SM_ENVIRONMENT, SM_SECRET_KEY, SM_VITE_DEV_URL,
SM_DEBUG, SM_LOG_LEVEL, SM_LOG_FORMAT, SM_MULTI_TENANT, SM_TENANT_HEADER
```

### Framework state

Framework singletons live on `app.state.sm`, a frozen `Services` dataclass populated
once at boot. Consumers read `request.app.state.sm.<field>` — never raw `app.state`
attributes for framework-owned state.

Fields: `settings`, `db`, `event_bus`, `menu_registry`, `permissions`,
`feature_flags`, `health_registry`, `i18n_registry`, `inertia_config`, `modules`.

Two attributes are intentionally kept outside `Services`:

- `app.state.inertia_dependency` — request-scoped `Depends` factory from fastapi-inertia.
- `app.state.migration` — dev-only boot-time check result, set in lifespan.

### Module settings

Module settings should:
- Use a per-module prefix: `SM_<MODULE>_*` (e.g. `SM_USERS_ALLOW_SIGNUP`).
- Be stored inside a module-owned dataclass at `app.state.<module_lower>` during `register_settings(app)`.
- `SM012` diagnostic fires if `register_settings` is overridden but no `app.state.<module_lower>` entry is added.

```python
class UsersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        from users.settings import UsersSettings
        from users.state import UsersState

        app.state.users = UsersState(settings=UsersSettings())
```

## Database

### Models

**SQLModel is the project-wide standard for every model — both DB tables and DTOs.** Table classes declare `table=True` and inherit the per-module `Base`; DTOs are plain `SQLModel` subclasses. No Pydantic `BaseModel` and no SQLAlchemy `DeclarativeBase` + `Mapped[...]`/`mapped_column` in module code.

```python
# modules/orders/orders/models.py
from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin
from sqlmodel import Field

Base = create_module_base("orders")

class Order(Base, AuditMixin, table=True):
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)

# modules/orders/orders/contracts/schemas.py
from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

class OrderOut(SQLModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

class OrderCreate(SQLModel):
    name: str = Field(min_length=1, max_length=200)
```

### Per-module Base

```python
from simple_module_db.base import create_module_base

Base = create_module_base("orders")   # provider auto-detected from SM_DATABASE_URL
```

- **PostgreSQL**: the module gets its own schema (`orders`). Tables live at `orders.<table>`.
- **SQLite**: single schema. Prefix `__tablename__` with the module name to avoid collisions (`orders_order`).

You can pin the provider for tests (`provider=DatabaseProvider.SQLITE`), but code that ships should let auto-detection handle it.

### Mixins

- `AuditMixin` — `created_at`, `updated_at`, `created_by`, `updated_by` (auto-populated from the current user in listeners).
- `SoftDeleteMixin` — `is_deleted`, `deleted_at`, `deleted_by`. `delete()` converts to soft-delete; `SELECT` auto-filters. Bypass with `stmt.execution_options(include_deleted=True)`.
- `MultiTenantMixin` — `tenant_id`. Auto-populated on insert; `SELECT` auto-filters when `current_tenant_id` is set.
- `VersionedMixin` — `version`, auto-incremented on update.

### Session lifecycle (`get_db`)

Each request opens one session:

- Commit fires on success **only if** the session has pending writes (`has_writes` flag set by `after_flush` listener, or live `.new/.dirty/.deleted`).
- Read-only requests exit via rollback — cheaper, and keeps the session out of write-side profiling.
- Exceptions always rollback.

Service code should not call `session.commit()` directly. Flush for intermediate reads if you need DB-assigned values, then let the dependency commit.

## Inertia

### Page keys

`inertia.render("<ModuleName>/<PageName>", ...)` maps to `modules/<name>/<name>/pages/<PageName>.tsx`.

- `<ModuleName>` is the PascalCase of the module directory: `blog_posts` → `BlogPosts`.
- Host-level pages under `client_app/pages/<PageName>.tsx` render with just `<PageName>` as the key (e.g. `inertia.render("Landing", ...)`).
- Mismatched keys fire `SM003` (orphan page) and `SM004` (phantom render) at diagnostic time.

### Shared props

`InertiaLayoutDataMiddleware` populates `request.state.inertia_shared` with:

- `auth.user`, `auth.isAuthenticated`, `auth.permissions` (expanded from roles).
- `menus` — grouped by `MenuSection` (sidebar, adminSidebar, navbar, userDropdown), role-filtered.

  Sidebar `order` follows banded ranges so installed modules sort into coherent groups:

  | Band      | Purpose             | Built-in modules                                            |
  |-----------|---------------------|-------------------------------------------------------------|
  | `10–99`   | Content / domain    | Dashboard (10), Products (20), Datasets (30), Files (40)    |
  | `100–199` | Administration      | Users (100), Feature Flags (110), Background Tasks (120)    |
  | `200+`    | System              | Settings (200)                                              |

  Pick a band by audience, leave gaps of ~10 between siblings, and put module-specific user-dropdown items in the `900+` range (Profile=990, Logout=999).

  Sidebar items can also set `group="<Label>"` on the `MenuItem` to render under a group header. The frontend clusters consecutive items with the same group label and prints the label as a section heading; the group's position is set by the lowest-`order` item that joins it. Built-in groups are `Content`, `Administration`, and `System`. Items with no `group` (the default) render flat — Dashboard intentionally stays ungrouped above the headed groups.
- `i18n` — active locale and translation bundle.

The framework does not know the shape of `auth.user`. A module (typically `users`) registers a `principal_serializer: Callable[[user], dict]` on `app.state` during `register_settings(app)`; the middleware calls it with `request.state.user` to build the `auth.user` payload. Without a registered serializer, `auth.user` is `None` even when a user is authenticated.

Use `InertiaDep` from `simple_module_hosting.inertia_deps` — it attaches the shared data automatically.

## Permissions

Modules declare permissions in `register_permissions(registry)` grouped by a name prefix:

```python
registry.add_group("Orders", [
    "orders.view", "orders.create", "orders.edit", "orders.delete",
])
```

Enforce with the `RequiresPermission` dependency:

```python
@router.post("/", dependencies=[Depends(RequiresPermission("orders.create"))])
async def create_order(...): ...
```

`DEFAULT_ROLE_PERMISSIONS` in `simple_module_hosting.permissions` ships only `admin: ["*"]`. Host apps configure their own role → permission map; the framework does not know about plugin permission strings.

## Events

Base class: `Event` from `simple_module_core.events`. Subclass per domain event:

```python
@dataclass
class OrderPlaced(Event):
    order_id: int
    total: Decimal
```

Subscribe in `register_event_handlers(bus)`:

```python
def register_event_handlers(self, bus: EventBus) -> None:
    bus.subscribe(OrderPlaced, self._on_order_placed)
```

Publish from anywhere with a bus handle:

```python
await bus.publish(OrderPlaced(order_id=42, total=Decimal("99")))
```

Dispatch walks the event's MRO, so subscribing to a base class delivers subclass events.

## Diagnostic codes

| Code | Level | Trigger |
|---|---|---|
| SM001 | ERROR | Module missing `meta` |
| SM003 | WARNING | `pages/<name>.tsx` exists but no matching `inertia.render()` call |
| SM004 | WARNING | `inertia.render("<Module>/<name>")` but no matching `.tsx` |
| SM007 | INFO | Module defines no `register_*` hooks |
| SM008 | ERROR | Duplicate module name / schema prefix conflict |
| SM009 | ERROR | Framework package directly imports from a plugin module |
| SM010 | ERROR | DB revision behind migration head |
| SM011 | WARNING | Module table not in migration history |
| SM012 | WARNING | `register_settings` overridden but nothing added to `app.state` |
| SM013 | WARNING | Locale file missing for a supported locale |
| SM014 | WARNING | Non-default locale missing keys present in the default |
| SM015 | WARNING | Non-default locale has keys not in the default |
| SM016 | ERROR | Locale JSON invalid or contains non-string leaves |

Diagnostics run automatically at boot — warnings print to stderr in dev, errors abort startup in production. There's no separate "run diagnostics" step in a scaffolded app: just start the server.

## Internationalization

Modules ship translations as JSON under `<package>/locales/<lang>.json` and declare them via `ModuleBase.locale_dirs()`:

```python
import importlib.resources
from pathlib import Path

class OrdersModule(ModuleBase):
    def locale_dirs(self) -> dict[str, Path]:
        return {"orders": Path(str(importlib.resources.files(__package__) / "locales"))}
```

`smpy create-module` scaffolds this method and a matching `locales/en.json` automatically.

### Key naming

Keys are namespaced by the module and hierarchical by area. Convention: `<namespace>.<area>.<string>` — e.g. `orders.browse.title`. Use `snake_case` for leaves. Nested JSON objects are flattened at boot — `{"browse": {"title": "X"}}` under namespace `orders` becomes `orders.browse.title` at runtime.

### Interpolation

Placeholders use `{name}` syntax, consistent between frontend and backend:

```json
{ "greeting": "Hello, {name}" }
```

```tsx
t('orders.greeting', { name: user.name })       // frontend
```

```python
t.t("orders.greeting", name=user.name)           # backend
```

Missing placeholders are left verbatim (`"Hello, {name}"`) rather than raising.

### Pluralization

Suffix keys with CLDR categories (`_zero`, `_one`, `_two`, `_few`, `_many`, `_other`); only `_other` is required. Pass `count` as a param:

```json
{
  "items_one": "{count} item",
  "items_other": "{count} items"
}
```

```tsx
t('orders.items', { count: items.length })
```

Backend uses Babel's CLDR plural rules; frontend uses i18next's `Intl.PluralRules`. Both follow the same CLDR categories, so behavior matches across the stack.

### Validation messages

Zod schemas with translated messages must be constructed **inside** a hook so they resolve against the active locale:

```ts
export function useProductSchema() {
  const { t } = useT();
  return z.object({
    name: z.string().min(1, t('products.validation.name_required')),
  });
}
```

Do NOT declare `const schema = z.object({ ... t('...') })` at module scope — it will resolve against whatever locale was active at first render, forever.

### Host and shared-package strings

- Host strings (landing page, error page) live in `host/locales/` and are namespaced `host.*`.
- Shared UI strings (`packages/ui/`) live in `packages/ui/locales/`, namespaced `ui.*`.
- Both are auto-discovered at boot alongside module contributions.

### Supported locales

Configure via env:

```
SM_I18N_DEFAULT_LOCALE=en
SM_I18N_SUPPORTED_LOCALES=en,es,de
SM_I18N_COOKIE_NAME=locale
```

The default locale must be in the supported list (enforced by a pydantic validator).

### Locale resolution order

Per request, `LocaleMiddleware` picks the active locale in this order:

1. Cookie named by `SM_I18N_COOKIE_NAME` (default `locale`), validated against `SM_I18N_SUPPORTED_LOCALES`.
2. `Accept-Language` header, with q-value parsing and longest-prefix match (`es-MX` → `es`).
3. `SM_I18N_DEFAULT_LOCALE`.

The active locale lands on `request.state.locale`. The `<LocaleSwitcher />` component POSTs to `/i18n/set-locale`, which sets a 1-year cookie and redirects back.

### Diagnostics

App boot runs `I18nDiagnostics` against every module's declared locale dirs. See codes `SM013`–`SM016` in the table above. Warnings are printed in dev; errors fail the boot in production.
