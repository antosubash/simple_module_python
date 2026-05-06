# settings

A DB-backed key/value store with system / tenant / user precedence, plus a per-module pydantic-settings registration system that lets every module's settings be edited from the admin UI and hot-reloaded at runtime.

Two distinct surfaces:

1. **Generic key/value settings** — anything addressable by a string `key`. Useful for arbitrary config you don't want to wedge into a pydantic class. Edited at `/settings`.
2. **Per-module pydantic settings** — each module registers a `BaseSettings` subclass via `register_module_settings`. Hydrated from the DB at boot, edited at `/settings/modules`, hot-swapped on save with a `SettingsReloaded` event so dependents (SMTP clients, Celery configs, …) can rebuild.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Settings` |
| `route_prefix` | `/api/settings` |
| `view_prefix` | `/settings` |
| `depends_on` | _(none)_ |

## Public API for module authors

### Register module settings

The pattern (pydantic `BaseSettings` subclass + `register_module_settings` in `register_settings`) is documented in [Per-module settings convention](/guide/configuration#per-module-settings-convention). What the settings module adds on top:

- **DB hydration**: `app.state.<package>.settings` is replaced with a fresh instance built from DB overrides + pydantic defaults during the host's hydrate phase, before `on_startup` runs.
- **Env-var migration**: `sm-settings import-from-env` scans every registered class's `env_prefix` and seeds matching `SM_*` env vars as SYSTEM-scoped rows. Idempotent.
- **Admin editing**: registered fields appear at `/settings/modules/<package>` with type-aware inputs.
- **Hot reload**: saving via the admin UI calls `apply_changes_and_reload`, which validates the diff against the pydantic class, persists deltas, swaps the live `app.state.<package>.settings`, and publishes [`SettingsReloaded`](#events) so dependents (SMTP clients, Celery configs, …) can rebuild.

### Read settings at request time (generic K/V)

```python
from settings.contracts import SettingsDep

@router.get("/check")
async def check(settings: SettingsDep) -> dict:
    if await settings.get_bool("orders.beta", default=False):
        ...
    timeout_ms = await settings.get_int("orders.timeout_ms", default=5000)
```

`SettingsDep` resolves a request-scoped `SettingsAccessor` bound to the current `user_id` + `tenant_id`. Lookups follow **USER → TENANT → SYSTEM → default** precedence.

| Method | Returns |
|---|---|
| `get(key, default=None)` | raw stored value |
| `get_str` / `get_bool` / `get_int` / `get_float` / `get_json` | typed helpers |
| `get_typed(key, default=None)` | resolves and casts using the row's stored `value_type` |
| `bind(user_id=..., tenant_id=...)` | a new accessor with overrides — useful for background jobs |
| `set_system(key, value, value_type=None, description=None)` | upsert at SYSTEM scope |
| `set_tenant(tenant_id, key, value, ...)` | upsert at TENANT scope |
| `set_user(user_id, key, value, ...)` | upsert at USER scope |

### Register a setting definition (so admins can see defaults)

```python
from settings.contracts import SettingsRegistry, SettingDefinition

class OrdersModule(ModuleBase):
    def register_settings(self, app):
        registry: SettingsRegistry = app.state.sm.settings_registry
        registry.add_definition(
            SettingDefinition(
                key="orders.beta",
                default="false",
                description="Enable the new checkout flow.",
            )
        )
```

The browse UI uses these definitions to render meaningful empty states for unset keys.

## Routes

### Generic K/V API (`/api/settings/...`)

All write endpoints require `settings.edit` / `settings.create` / `settings.delete`; reads need `settings.view`.

| Method + path | Purpose |
|---|---|
| `GET /api/settings/` | list all (`?scope=&scope_id=`) |
| `GET /api/settings/resolve/{key}` | precedence resolution (`?user_id=&tenant_id=`) |
| `GET / PUT / DELETE /api/settings/system/{key}` | system-scope CRUD |
| `GET / PUT / DELETE /api/settings/tenant/{scope_id}/{key}` | tenant-scope CRUD |
| `GET / PUT / DELETE /api/settings/user/{scope_id}/{key}` | user-scope CRUD |
| `POST /api/settings/` | create with explicit `scope` + `scope_id` (`SettingCreate`) |
| `GET / PUT / DELETE /api/settings/{setting_id}` | by-id CRUD |

### Module settings API

| Method + path | Purpose |
|---|---|
| `GET /api/settings/modules` | autodiscovered per-module settings + current values |
| `PUT /api/settings/modules/{package}` | apply field changes; hot-reload |
| `DELETE /api/settings/modules/{package}/{field}` | revert one field to its pydantic default |

### View

| Method + path | Inertia component |
|---|---|
| `GET /settings/` | `Settings/Browse` |
| `GET /settings/create` | `Settings/Create` |
| `GET /settings/{setting_id}/edit` | `Settings/Edit` |
| `GET /settings/modules` | `Settings/ModulesEdit` |
| `POST` / `PUT` / `DELETE /settings/...` | form actions; redirect to `/settings` |

## Public contracts

```python
from settings.contracts import (
    SettingOut, SettingCreate, SettingUpdate, SettingUpsert,
    SettingScope, SettingValueType,
    SettingsAccessor, SettingsDep, SettingsRegistry, SettingDefinition,
    SettingsReloaded,
)
```

| Class | Purpose |
|---|---|
| `SettingOut` | Persisted row: `id`, `scope`, `scope_id`, `key`, `value`, `value_type`, `description`, `created_at`, `updated_at`. |
| `SettingScope` (enum) | `SYSTEM` / `TENANT` / `USER`. |
| `SettingValueType` (enum) | `STRING` / `BOOL` / `INT` / `FLOAT` / `JSON`. |
| `SettingsAccessor` | Request-scoped facade (described above). |
| `SettingsRegistry` | In-memory definition registry. |
| `SettingsReloaded` (event) | Published after `apply_changes_and_reload`. Fields: `package: str`, `changed: tuple[str, ...]`. |

## Models

`Setting` (table `settings_setting`)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` | PK |
| `scope` | `str` | `system` \| `tenant` \| `user`; indexed |
| `scope_id` | `str` | empty string for system scope; indexed |
| `key` | `str` | indexed |
| `value` | `str` | string-encoded; cast via `value_type` |
| `value_type` | `str` | `string` (default), `bool`, `int`, `float`, `json` |
| `description` | `str \| None` | |
| audit | from `AuditMixin` | |

Unique constraint on `(scope, scope_id, key)`.

## Lifecycle (boot + reload)

1. **`register_settings`** (each module) — calls `register_module_settings(app, package, cls, services_factory)`. The settings module records the entry in a process-global registry; `app.state.<package>` is populated with pydantic defaults so even modules that boot before hydrate has run see usable values.
2. **`on_startup` (settings module)** — opens a session and calls `hydrate_settings(cls, store, package)` per registered module, replacing each `app.state.<package>.settings` with a fresh pydantic instance built from DB overrides + defaults.
3. **At runtime** — admin saves via `PUT /api/settings/modules/{package}`. `apply_changes_and_reload(app, bus, store, package, changes)` validates the diff against the pydantic class, persists deltas, hot-swaps `app.state.<package>.settings`, publishes `SettingsReloaded(package, changed=(...))`.
4. **Subscribers** — modules listen for `SettingsReloaded` and rebuild stateful handles (e.g. the SMTP client) when their package matches.

## Permissions

| Code | Purpose |
|---|---|
| `settings.view` | read settings |
| `settings.create` | create new K/V rows |
| `settings.edit` | update existing rows / module fields |
| `settings.delete` | delete rows / clear module fields |

## Menu

| Label | URL | Icon | Section | Group | Order |
|---|---|---|---|---|---|
| `Settings` | `/settings` | `settings` | `SIDEBAR` | `System` | `200` |

## Events

- `SettingsReloaded(package, changed)` — published after a successful module-settings save.

## CLI

- `sm-settings import-from-env` — one-shot migration. Walks every module that has registered settings; for each `SM_<PREFIX>_<FIELD>` env var present, writes a SYSTEM-scope row so the value persists without needing the env var any longer. Idempotent — only seeds keys that don't already have a DB override.

## Inertia pages

- `Settings/Browse.tsx` — generic K/V browse + filter.
- `Settings/Create.tsx`, `Settings/Edit.tsx` — generic K/V CRUD forms.
- `Settings/ModulesEdit.tsx` — per-module settings panel; one section per registered module.

## Locales

Top-level keys in `settings/locales/en.json`: `browse`, `table`, `scopes`, `value_types`, `form`, `create`, `edit`, `modules`.

## Notes

- The K/V store treats `value` as a string and casts on read using `value_type` — that's deliberate: it lets you store anything (including JSON blobs) without a per-type column.
- `register_module_settings` does **not** require a `services_factory` — pass `None` if you only want hydration without a state container — but the convention is to always have one so dependents can `app.state.<package>.something_else = ...` later.
