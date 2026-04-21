# DB-backed Module Settings with Admin UI

**Date:** 2026-04-21
**Status:** Design — approved for implementation planning

## Goal

Collapse the `.env` surface to a four-variable bootstrap and move every other configuration value into the database, editable through a typed per-module admin UI. Defaults stay in code (pydantic `BaseSettings` subclasses); DB rows override defaults; the UI is the primary interface for operators.

## Scope

**In scope.**
- Replace `SM_<MODULE>_*` env reading with DB-backed resolution for every module's `BaseSettings`.
- New admin UI at `/settings/modules` (replaces today's read-only view) — sidebar + main panel, typed inputs, per-module save, per-field reset-to-default.
- Hot-reload on save: rebuild `app.state.<package>.settings` and fire a `settings.reloaded` event.
- Secret fields masked in UI (write-only).
- One-shot `sm-settings import-from-env` CLI to migrate existing deployments.

**Out of scope.**
- Tenant-scoped and user-scoped overrides in the new UI. The existing free-form `/settings` Browse/Create/Edit pages — which already support all three scopes — stay for power users.
- Encryption-at-rest for secrets. Secrets live plaintext in the `Setting` table; the UI masks on display.
- Config-file layer (YAML/TOML). DB is the only override source.

## Non-goals & invariants

- **BaseSettings stays the schema source of truth.** All defaults, types, `Field(description=...)`, and `model_validator` logic remain in each module's settings class. The DB stores only overrides.
- **No env-var fallback.** After this change, setting `SM_USERS_ALLOW_SIGNUP=true` in the environment has no effect. This is an intentional clean cut — see Migration below.
- **The free-form `Setting` CRUD and its scoped resolution are preserved.** This feature adds a namespaced view on top; it does not rewrite the scoped resolver.

## Env-var surface after change

```
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db
SM_ENVIRONMENT=development
SM_SECRET_KEY=change-me-in-production
SM_VITE_DEV_URL=http://localhost:5050
```

These four are the **bootstrap group**: needed before the DB is available (`SM_DATABASE_URL`), before strict-discovery runs (`SM_ENVIRONMENT`), before `SessionMiddleware` is mounted (`SM_SECRET_KEY`), or before Vite asset URLs are computed in dev (`SM_VITE_DEV_URL`). They stay env-only and load via a new `BootstrapSettings` class in `framework/hosting`.

Everything else — `SM_USERS_*`, `SM_BG_TASKS_*`, `SM_DATASETS_*`, `SM_FILE_STORAGE_*`, `SM_SETTINGS_*`, plus non-bootstrap host fields (`multi_tenant`, `tenant_header`, `i18n_default_locale`, etc.) — moves to DB.

## Architecture

Four pieces:

### 1. `SettingsStore` (new, in `settings` module)

Thin wrapper over the existing `SettingService` that speaks in terms of `(package, field_name)` pairs, hard-coded to `scope=SYSTEM`, `scope_id="system"`. Provides:

```python
class SettingsStore:
    def __init__(self, service: SettingService) -> None: ...

    async def get_overrides(self, package: str) -> dict[str, str]:
        """All stored overrides for a module, as raw string values."""

    async def set_override(self, package: str, field: str, value: str, value_type: str) -> None: ...

    async def clear_override(self, package: str, field: str) -> None: ...

    async def list_packages(self) -> list[str]: ...
```

Keys in the `Setting` table are written as `"<package>.<field>"` to avoid collision with user-defined free-form keys. `scope="system"`, `scope_id="system"`.

### 2. `load_settings` / `hydrate_settings`

```python
def load_settings(cls: type[T]) -> T:
    """Construct a BaseSettings using pydantic defaults only (no DB, no env)."""

async def hydrate_settings(cls: type[T], store: SettingsStore, package: str) -> T:
    """Return a BaseSettings where each field is (DB value > default)."""
```

`hydrate_settings` reads raw string overrides, parses each according to `value_type`, and builds the settings with `cls(**parsed_overrides)`. Pydantic runs field validators and `model_validator` — any failure raises with per-field error info.

### 3. Hot-reload mechanism

The settings module owns a registry: `{package: BaseSettings_subclass}`, populated during `register_settings` of each module via a small helper:

```python
def register_module_settings(app: FastAPI, package: str, cls: type[BaseSettings]) -> None:
    """Install defaults on app.state.<package>.settings and register the class
    for later hydration / reload."""
```

On save (API endpoint):
1. Look up the registered `cls` for the package.
2. Merge requested changes with existing DB overrides.
3. Construct `cls(**merged)` — fails loudly with pydantic validation errors.
4. Write changed rows to `Setting` via `SettingsStore`.
5. Reassign `app.state.<package>.settings = new_instance`.
6. Fire `settings.reloaded` event with `{package, changed: [field_names]}`.

### 4. UI (`/settings/modules`)

Sidebar + main panel. See Section 4 of the brainstorm for the full layout; key pieces:

- Sidebar lists registered modules, with search that also fuzzy-matches field names.
- Main panel renders the selected module's fields as a typed form, grouped by optional `group` metadata. Save button is disabled until dirty.
- Per-field "Reset to default" link; "Requires restart" badge when applicable.
- Secret fields masked with "Set new value" toggle.
- Validation errors from the save attempt surface inline.
- Link back to the existing `/settings` free-form Browse for power users.

Permissions: reuse the existing `settings.manage` permission from `modules/settings/settings/constants.py`.

## Data model & value encoding

Reuse the existing `Setting` table — no migration needed:

- `key = "<package>.<field>"`
- `scope = "system"`, `scope_id = "system"`
- `value` — string; for complex types, JSON-encoded
- `value_type` — one of `"string" | "bool" | "int" | "float" | "json"`; drives the hydrator's parsing
- `description` — mirror of `Field(description=...)` for reference; not source of truth

Secret classification reuses the existing `_SECRET_PATTERNS` regex in `_module_settings.py` (`password|secret|api_key|private_key|token_secret`). Secrets are plaintext in `Setting.value` but masked (`••••••••`) in API responses; on update, the mask sentinel is treated as "no change".

### Field-level metadata

`_module_settings.py` is extended so each discovered field exposes:
- `type` — one of `bool | int | float | string | select | json`
- `enum_values` — populated when the pydantic field uses `Literal[...]` or `Field(pattern="^(a|b)$")` with a parseable pattern
- `is_secret` — via the existing regex
- `requires_restart` — read from `json_schema_extra={"requires_restart": True}` on the pydantic `Field(...)`
- `group` — optional subsection label (`"SMTP"`, `"Rate limiting"`), read from the same `json_schema_extra`

Modules opt into `requires_restart` / `group` by annotating fields — see the "requires_restart fields" table below.

## Boot order

Today's sequence (from `CLAUDE.md`):

> `register_settings` → `register_menu_items` / ... → `register_routes` → `on_startup` (topological order)

The DB engine is created by the hosting layer **before** module hooks run, but sessions are per-request — we don't run module code against the DB during `register_settings`. Therefore:

- **`register_settings`** installs `app.state.<package>.settings` populated with **pydantic defaults only**. This preserves the invariant that downstream hooks (menu, permissions, routes) can read settings.
- **Hosting lifespan hydrates before any module `on_startup` runs.** The hosting layer (not a module) owns a "hydrate-all" step at the very start of the FastAPI lifespan: open a DB session, iterate the registered module-settings classes, reassign each `app.state.<package>.settings`, then dispatch module `on_startup` hooks. This guarantees every module sees DB-hydrated values during its own startup (important for e.g. `background_tasks` configuring Celery from `broker_url`).
- **Request handlers** always see DB-hydrated values.
- **Stateful handles built at boot** (SMTP client, Celery broker config, middleware `secret_key`) either (a) subscribe to `settings.reloaded` and rebuild themselves, or (b) declare `requires_restart=True` on the field — see the table below.

## `requires_restart` fields

| Module | Field | Why |
|---|---|---|
| `background_tasks` | `broker_url` | Celery worker reads this in a separate process; reload doesn't reach it |
| `background_tasks` | `result_backend` | Same reason |
| `users` | `cookie_secure` | Applied to `SessionMiddleware` at `add_middleware` time; Starlette middleware is frozen after `app` is built |
| `users` | `cookie_name`, `cookie_samesite`, `cookie_max_age_seconds` | Same middleware-freeze reason |

All other fields are hot-reloadable. The SMTP mailer in `users` subscribes to `settings.reloaded` and rebuilds its client on any change to `smtp_*` or `mailer` fields.

Bootstrap fields (`SM_DATABASE_URL`, `SM_ENVIRONMENT`, `SM_SECRET_KEY`, `SM_VITE_DEV_URL`) don't appear in the UI — they're not in the DB.

## API surface (new endpoints)

Added under the existing settings router:

- `GET /settings/api/modules` — list of registered modules with current hydrated values, defaults, metadata (types, enums, groups, `requires_restart`, `is_secret`). Secrets returned masked.
- `PUT /settings/api/modules/{package}` — body `{field_name: new_value, ...}`. Validates by constructing `cls(**merged)`; on success writes deltas and fires reload. Mask sentinel on a secret field = "no change".
- `DELETE /settings/api/modules/{package}/{field}` — clear a single override (reset to default). Triggers reload.

View endpoints:
- `GET /settings/modules` — replaces the existing read-only Inertia page. Props include the same data as the API response.

## Failure modes & edge cases

- **Pydantic validation fails on save.** UI shows per-field errors; no DB write; `app.state` unchanged.
- **Pydantic validation fails during `on_startup` hydrate.** The field's DB row is bad (e.g. schema changed between releases). Log a warning, keep the default for that field, continue booting. The UI flags the field as "stored value invalid — using default".
- **A module disappears between releases.** Its `Setting` rows become orphaned. `make doctor` gets a new `SM018` warning listing orphan settings rows; a separate CLI `sm-settings prune-orphans` removes them.
- **Concurrent edits.** Last write wins (there's no optimistic concurrency today on `Setting`). Acceptable — admin UI with low write rate.
- **Placeholder token-secret check.** `UsersSettings.model_validator` fires during DB hydration in production. On boot: blocks startup (matches current behavior). On UI save: returns validation error.

## Migration

- **No Alembic migration** — `Setting` table already exists.
- **`sm-settings import-from-env` CLI** — one-shot: reads `SM_<MODULE>_*` from the current process environment, writes corresponding rows to `Setting` for each registered module. Idempotent.
- **Release note** — deployments must run `sm-settings import-from-env` after upgrade (or accept that all modules revert to defaults).
- **Per-module code changes:**
  - Remove `env_prefix` and `env_file` from `SettingsConfigDict`.
  - `register_settings` calls `register_module_settings(app, package, SettingsCls)`; the helper installs defaults on `app.state.<package>.settings`.
  - Services that previously received `settings=SettingsCls()` now receive the default instance, and re-read from `app.state` on reload via the event subscription.
- **Host-level split:**
  - `BootstrapSettings` — the four env vars, read at boot. Lives in `framework/hosting`.
  - `HostSettings` — `multi_tenant`, `tenant_header`, `i18n_default_locale`, `i18n_supported_locales`, `i18n_cookie_name`, plus anything else currently on the monolithic `HostingSettings` minus the bootstrap four. DB-backed via the same `register_module_settings` helper under `package="host"`.
- **`.env.example`** — rewritten to the four bootstrap vars; everything else removed.
- **`docker-compose.yml`** — removes `SM_BG_TASKS_BROKER_URL` / `SM_BG_TASKS_RESULT_BACKEND` environment entries; the Redis defaults in `BackgroundTasksSettings` are updated to `redis://redis:6379/*` (matching the compose Redis service hostname). Dev-outside-compose users run `sm-settings import-from-env` or set overrides in the UI.
- **`README.md`** — env-var table shrinks to four rows + a pointer to `/settings/modules`.

## Tests

- **New:**
  - `modules/settings/tests/test_store.py` — round-trip for `SettingsStore` (`set_override`, `get_overrides`, `clear_override`).
  - `modules/settings/tests/test_hydrate.py` — `hydrate_settings` parses each `value_type` correctly; falls back to defaults; pydantic validation errors surface.
  - `modules/settings/tests/test_module_settings_api.py` — GET/PUT/DELETE on the new endpoints; mask sentinel handling; validation error propagation.
  - `modules/settings/tests/test_hot_reload.py` — save → `app.state.<package>.settings` is reassigned; `settings.reloaded` event fires with the right payload.
  - `tests/test_bootstrap_settings.py` — the four bootstrap env vars load correctly; missing `SM_SECRET_KEY` fails boot with a clear message.
- **Updated:**
  - `modules/users/tests/test_settings.py` — tests that currently `monkeypatch.setenv("SM_USERS_*", ...)` are rewritten to write via `SettingsStore` and hydrate. The placeholder-secret production check becomes a hydrate-time test.
  - `tests/conftest.py` — adds a `settings_store` fixture; `app` fixture gains a `settings_overrides` param so tests can preload overrides before `on_startup`.
- **E2E:**
  - `tests/e2e/test_settings_ui.py` — log in as admin, navigate to `/settings/modules`, toggle `users.allow_signup` to `true`, confirm `/users/register` becomes reachable without a restart.

## Diagnostics

- Existing `SM012` (`register_settings` overridden but nothing on `app.state.<module>`) is still emitted — the `register_module_settings` helper satisfies it automatically.
- New `SM018` — orphan `Setting` rows for packages that no longer register a BaseSettings class. Warning level; fixable via `sm-settings prune-orphans`.

## Ship criteria

- `make test` green.
- `make lint` green, including the 300-line file cap. `_module_settings.py` is ~153 lines today; the metadata extensions should stay under the cap or split into a sibling module.
- `make doctor` green.
- Manual: `/settings/modules` renders, editing `users.allow_signup` takes effect without restart, editing `background_tasks.broker_url` shows the "requires restart" badge.
- `sm-settings import-from-env` run against a dev `.env` successfully populates the `Setting` table.

## Open decisions (to resolve during plan writing)

- Exact shape of the `json_schema_extra` metadata conventions — may land as a small helper (`module_field(...)` wrapping `Field`) to keep module code readable.
- Whether `settings.reloaded` events are sync or async on the bus. If the bus is already async, follow that; otherwise punt to sync with a TODO.
- Whether `list_packages` iterates the registry or reads distinct `package` values from `Setting`. Registry is faster and is the source of truth during the app's lifetime; DB-scan is needed for `prune-orphans`.
