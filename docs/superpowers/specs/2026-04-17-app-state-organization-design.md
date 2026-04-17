# App state organization — design

**Date:** 2026-04-17
**Scope:** Framework hygiene pass targeting `app.state` bloat.

## Motivation

`app.state` has accreted 15+ loose attributes mixing framework singletons (`menu_registry`, `perm_registry`, `event_bus`, `db`, `i18n_registry`, …) with module-owned state (`mailer`, `rate_limiter`, `auth_throughput_limiter`, `users_settings`, `auth_settings`, `users_roles_cache`). Three attributes are pure duplication of fields already on `settings` (`settings_default_locale`, `settings_supported_locales`, `settings_cookie_name`). Naming is inconsistent (some keys module-prefixed, some not). No typing: consumers use `request.app.state.x` with no autocomplete or static verification.

This is organization debt, not a performance problem or a bug. The fix is to replace loose keys with typed namespace objects — one slot for framework singletons, one slot per module — keeping `app.state` as the storage mechanism.

## Goals

- One typed entry on `app.state` per owner (framework + each module).
- Delete duplicate locale fields.
- Establish a convention module authors can follow mechanically.
- Zero-churn to FastAPI's DI and middleware patterns.

## Non-goals

- Not introducing a `Services`/DI container library.
- Not moving to module-level service globals (evaluated and declined — trades multi-app/test-isolation for an aesthetic gain with no perf benefit).
- Not wrapping every service in a `Depends` helper. Keep existing surgical deps that do real work (`DbDep`, `InertiaDep`, `TranslatorDep`, `RequiresPermission`).
- Not collapsing the three framework packages (`core` / `hosting` / `db`). Evaluated and deferred — unrelated churn with a different blast radius.
- Not renaming the `register_settings` hook. Convention broadens; name stays.

## Design

### Framework `Services` — single slot at `app.state.sm`

New module `framework/core/simple_module_core/services.py` defines:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    db: DatabaseState
    event_bus: EventBus
    menu_registry: MenuRegistry
    permissions: PermissionRegistry
    feature_flags: FeatureFlagRegistry
    health_registry: HealthRegistry
    i18n_registry: I18nRegistry
    modules: tuple[ModuleBase, ...]
```

Populated once inside `create_app`, stored as `app.state.sm`. Consumers read `request.app.state.sm.event_bus` (or `app.state.sm.event_bus` for middleware/lifespan).

Frozen + slotted:
- Frozen keeps the intent "set once at boot" enforced at runtime — no middleware scribbling over singletons.
- Slotted prevents silent attribute additions (which is how the loose-keys state grew in the first place) and is marginally faster for attribute access.

### What stays loose on `app.state` (by design)

- **`app.state.inertia_dependency`** — request-scoped `Depends` callable wired by fastapi-inertia. Belongs where FastAPI expects it.
- **`app.state.migration`** — dev-only boot-time check result, read once by a development warning. Ephemeral boot state, not a long-lived service.
- **`app.state.inertia_config`** — kept on `Services` (used by `host/templates/index.html` and `_error_handlers.py:25`, both request-path singletons). Added to the dataclass above.

### Deletions

- `app.state.settings_default_locale`, `app.state.settings_supported_locales`, `app.state.settings_cookie_name` — pure duplicates of `settings.i18n_default_locale`, `settings.i18n_supported_locales`, `settings.i18n_cookie_name`. Consumers in `host/routes_i18n.py` + `host/tests/test_routes_i18n.py` switch to reading `settings` directly.
- The `state_before`/`state_after` drift detection in `app_builder.py:176-182` — the explicit dataclass removes the need for runtime drift detection.

### Module pattern — one slot at `app.state.<module_lower>`

Each module owns a single slot holding a module-defined dataclass. Example for the users module (`modules/users/users/services.py`):

```python
@dataclass
class UsersServices:
    settings: UsersSettings
    mailer: Mailer
    rate_limiter: ThroughputLimiter
    auth_throughput_limiter: ThroughputLimiter
    roles_cache: RolesCache
```

Module's `register_settings(app)` assigns the dataclass:

```python
app.state.users = UsersServices(settings=..., mailer=..., ...)
```

Module services are **not** frozen. Fields that depend on boot-later resources (e.g. `roles_cache` needs the DB) are constructed with `field(default=None)` and populated in `on_startup`. Convention says "set once during boot, treat as read-only after." No enforcement; small surface.

### Migration table

| Today | New |
|---|---|
| `app.state.users_settings` | `app.state.users.settings` |
| `app.state.mailer` | `app.state.users.mailer` |
| `app.state.rate_limiter` | `app.state.users.rate_limiter` |
| `app.state.auth_throughput_limiter` | `app.state.users.auth_throughput_limiter` |
| `app.state.users_roles_cache` | `app.state.users.roles_cache` |
| `app.state.auth_settings` | `app.state.auth.settings` |
| `app.state.menu_registry` | `app.state.sm.menu_registry` |
| `app.state.perm_registry` | `app.state.sm.permissions` |
| `app.state.ff_registry` | `app.state.sm.feature_flags` |
| `app.state.event_bus` | `app.state.sm.event_bus` |
| `app.state.health_registry` | `app.state.sm.health_registry` |
| `app.state.settings` | `app.state.sm.settings` |
| `app.state.i18n_registry` | `app.state.sm.i18n_registry` |
| `app.state.db` | `app.state.sm.db` |
| `app.state.modules` | `app.state.sm.modules` |
| `app.state.inertia_config` | `app.state.sm.inertia_config` |
| `app.state.settings_default_locale` | deleted; read `settings.i18n_default_locale` |
| `app.state.settings_supported_locales` | deleted; read `settings.i18n_supported_locales` |
| `app.state.settings_cookie_name` | deleted; read `settings.i18n_cookie_name` |

## Diagnostics & docs

- **SM012** (today: "`register_settings` overridden but nothing added to `app.state`") — re-aim at checking for `app.state.<module>` presence. Same intent, new shape.
- **`docs/framework-conventions.md`** — the "Settings" section convention moves from "store as `app.state.<module>_settings`" to "store as `app.state.<module>`, a module-owned dataclass". Add a short example.
- **Scaffolding** — `scripts/new_module.py` + `framework/hosting/simple_module_hosting/templates/module/**` emit a `services.py` with a starter `<Module>Services` dataclass, plus `register_settings` boilerplate that assigns `app.state.<module>`.

## Rollout

Each step is independently revertable and does not require coordinated cross-cutting changes:

1. **Land `Services` + populate `app.state.sm`** alongside existing writes. Both coexist; nothing breaks. Ship.
2. **Migrate framework consumers** (`middleware.py`, `_error_handlers.py`, `health.py`, `inertia_deps.py`, `i18n_deps.py`, `_inertia_setup.py`, `permissions.py`) to read `app.state.sm.x`. Old keys still written. Ship.
3. **Migrate module consumers**, one module at a time (users, then auth). Each commit adds `services.py`, sets `app.state.<module>`, migrates consumers, deletes old loose writes. Ship per module.
4. **Delete old framework keys + duplicates + drift detection.** Ship.
5. **Update docs + scaffolding templates.** Ship.

No compat shims. No deprecation period — keys are framework-internal, not public API. A migration note in the changelog covers external consumers (none known).

## Test impact

Fixtures currently reaching `app.state.<x>` switch to `app.state.sm.<x>` or `app.state.<module>.<x>`. No new fixture primitives, no `dependency_overrides`, no teardown changes.

## Call-site summary

Approximate counts for planning:

| Bucket | Files | Call-sites |
|---|---|---|
| Framework consumers | `middleware.py`, `_error_handlers.py`, `health.py`, `inertia_deps.py`, `i18n_deps.py`, `_inertia_setup.py`, `permissions.py` | ~15 |
| Duplicate locale removal | `host/routes_i18n.py`, `host/tests/test_routes_i18n.py` | 5 |
| Users module | `modules/users/**`, `modules/users/tests/**` | ~18 |
| Auth module | `modules/auth/**`, `modules/auth/tests/**` | ~4 |
| Scaffolding + docs + cleanup | `scripts/`, templates, `framework-conventions.md`, `app_builder.py` drift block | ~10 |

## Alternatives considered

- **Module-level service globals** (`from simple_module.services import get_services`) — simpler consumption pattern, but trades multi-app / test-isolation properties for an aesthetic gain with no perf benefit. Declined.
- **`Depends` wrapper layer over every service** (`EventBusDep`, `MenuRegistryDep`, …) — idiomatic FastAPI, but adds one wrapper per service for a test-override capability the project rarely uses (tests are integration-style). Declined.
- **Strip duplicates only, leave the rest** — one-hour change, but doesn't address the organizational bloat the user named. Declined.

## Risks

- Staged rollout means old and new shapes coexist briefly on `app.state`. Intentional, and the drift is short-lived (steps 1–4).
- Non-frozen module services rely on convention ("set once during boot, read-only after"). If a module violates this, bugs are localized to that module, not the framework.
