# Module Lifecycle Hooks: Exception Handlers, Health Checks, Module Settings

> **Note (2026-04-15):** Keycloak integration was removed; see plan
> `cryptic-juggling-lightning`. References to "Keycloak" below are
> historical context from the original design — the patterns still apply.

**Date**: 2026-04-13
**Status**: Draft
**Scope**: Add three new lifecycle hooks to `ModuleBase` and restructure `create_app()` sequencing

## Problem

The framework hardcodes behavior that should be module-driven:

1. **Exception handlers** — modules cannot register custom exception handlers (e.g., auth redirect on 401, validation error formatting)
2. **Health checks** — `/health/ready` returns a static response; modules cannot report their own health (e.g., Keycloak reachability, search index status)
3. **Settings** — the framework's `Settings` class contains `keycloak_*` fields that only the auth module uses; new modules would need to modify the framework to add their config

## Design

### Hook 1: `register_exception_handlers(app: FastAPI)`

**Pattern**: Direct `app` access (same as `register_middleware`).

```python
# ModuleBase — no-op default
def register_exception_handlers(self, app: FastAPI) -> None: ...
```

Modules call `app.add_exception_handler(exc_class, handler)` directly. The Inertia version conflict handler stays hardcoded in `app_builder.py` — it's framework infrastructure.

**Called**: After Inertia exception handler, before middleware setup.

### Hook 2: `register_health_checks(registry: HealthRegistry)`

**Pattern**: Registry-based (same as `MenuRegistry`, `PermissionRegistry`).

New types in `simple_module_core.health`:

```python
class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthCheckResult:
    status: HealthStatus
    detail: str | None = None

# The callable signature for a health check
HealthCheckFn = Callable[[], Awaitable[HealthCheckResult]]

@dataclass
class HealthCheck:
    name: str
    check: HealthCheckFn

class HealthRegistry:
    def add(self, check: HealthCheck) -> None
    @property
    def all_checks(self) -> list[HealthCheck]
```

**ModuleBase hook**:

```python
def register_health_checks(self, registry: HealthRegistry) -> None: ...
```

**Changes to `health.py`**: The `/health/ready` endpoint receives the registry via `app.state.health_registry` and runs all checks concurrently via `asyncio.gather`. Returns per-component status:

```json
{
  "status": "degraded",
  "checks": {
    "keycloak": {"status": "healthy"},
    "search_index": {"status": "degraded", "detail": "reindexing in progress"}
  }
}
```

Overall status = worst individual status (unhealthy > degraded > healthy).

If a check raises an exception, it's caught and reported as `unhealthy` with the exception message as `detail`. This prevents a single broken check from crashing the entire health endpoint.

`/health` and `/health/live` remain static — they indicate the process is running, not that dependencies are ready.

### Hook 3: `register_settings(app: FastAPI)`

**Pattern**: Direct `app` access. Each module declares its own `BaseSettings` subclass.

```python
# ModuleBase — no-op default
def register_settings(self, app: FastAPI) -> None: ...
```

**Convention**: Modules store their settings on `app.state` using `<module_name_lower>_settings`:

```python
# In sm_auth/settings.py
class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SM_AUTH_")
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "simple-module"
    keycloak_client_id: str = "simple-module-app"
    keycloak_client_secret: str = ""


# In AuthModule
def register_settings(self, app: FastAPI) -> None:
    from sm_auth.settings import AuthSettings

    app.state.auth_settings = AuthSettings()
```

**Framework Settings cleanup**: Remove `keycloak_url`, `keycloak_realm`, `keycloak_client_id`, `keycloak_client_secret` from the framework's `Settings` class. These move into `AuthSettings`.

**AuthModule update**: `register_middleware` reads from `app.state.auth_settings` instead of `app.state.settings`.

## Sequencing: The `create_app()` Boot Order

### Current order and the problem

```
1. Load Settings
2. Discover & sort modules
3. Run diagnostics
4. Collect registrations (menu, permissions, flags, events)
5. Init database
6. Create FastAPI app          ← app created HERE
7. Store registries on app.state
8. Inertia setup
9. Exception handlers
10. Middleware pipeline
11. Register routes
12. Health endpoints
13. Static files
```

`register_settings(app)` needs to run before all other module hooks (modules may need their settings during registration). But `app` isn't created until step 6.

### Solution: Move app creation earlier

There's no real dependency keeping `app` creation at step 6. The `lifespan` closure only needs `modules`, which is available after step 2. Move app creation + state setup to right after diagnostics:

```
1.  Load Settings
2.  Discover & sort modules
3.  Run diagnostics
4.  Create FastAPI app + store framework settings on app.state
5.  register_settings(app)        ← modules load their own settings
6.  Collect registrations (menu, permissions, flags, events)
7.  register_health_checks(registry)
8.  Init database
9.  Inertia setup
10. register_exception_handlers(app)
11. Middleware pipeline (incl. register_middleware)
12. Register routes
13. Health endpoints (registry available)
14. Static files
```

This is clean because:
- `app.state` is available for all module hooks
- Registry-based hooks (menu, permissions, flags, events, health) don't need `app` — they get their registry object
- `app`-based hooks (settings, exception handlers, middleware) have `app` available
- Health checks are registered before the health router is mounted

### Detecting sequencing violations at dev time

When a module calls `app.state.<something>` during the wrong phase, it fails silently or with a cryptic `AttributeError`. We should catch these early.

**Approach: Diagnostic check SM010 — settings not registered**

Add a diagnostic that verifies `register_settings` implementations follow the convention. After `register_settings` runs for all modules, log which modules registered settings and what `app.state` keys they set. This is informational, not blocking.

**Approach: Runtime guard on `app.state` access during boot**

Not worth the complexity. The hook ordering is deterministic and documented. If a module tries to read `app.state.auth_settings` during `register_menu_items`, it gets a clear `AttributeError` pointing to `auth_settings` — that's already a good enough signal. Adding a custom `__getattr__` wrapper around `app.state` would be fragile and hard to remove.

**What we will do**:

1. Document the hook execution order clearly in `ModuleBase` docstring.
2. Add a runtime settings validation in `app_builder.py` (not in `ModuleDiagnostics`) that runs immediately after all `register_settings` calls. The existing `ModuleDiagnostics.run()` executes at step 3 (before `app` exists), so it cannot validate `app.state`. This new check runs at step 7 in `create_app()`, dev-mode only.

### SM010 runtime check: settings registration validation

Implemented in `app_builder.py`, not in `diagnostics.py`. After all `register_settings` calls complete:

1. Snapshot `app.state` keys before and after the `register_settings` loop.
2. For each module that overrides `register_settings` (check via `cls.__dict__`), verify at least one new key was added.
3. If not, log a warning using the `Diagnostic` dataclass for consistent formatting:

```
⚠ SM010 [WARNING] Auth: register_settings() was overridden but added nothing to app.state
  ↳ Suggestion: Store your settings on app.state (e.g., app.state.auth_settings = AuthSettings())
```

This is a warning (not an error) — a module might legitimately override `register_settings` to configure something other than `app.state` in the future, though that would be unusual.

## Files Changed

### Framework core (`simple_module_core`)

| File | Change |
|------|--------|
| `module.py` | Add `register_exception_handlers`, `register_health_checks`, `register_settings` hooks; update class docstring with hook execution order |
| `health.py` | **New file** — `HealthStatus`, `HealthCheckResult`, `HealthCheck`, `HealthRegistry` |
| `diagnostics.py` | Add SM010 check; add new hooks to `_check_empty_modules` method list |
| `__init__.py` | Export new health types |

### Framework hosting (`simple_module_hosting`)

| File | Change |
|------|--------|
| `app_builder.py` | Restructure `create_app()` to new boot order; call new hooks; create `HealthRegistry` |
| `health.py` | Update `/health/ready` to use `HealthRegistry`; run checks with `asyncio.gather` |
| `settings.py` | Remove `keycloak_*` fields |

### Auth module (`sm_auth`)

| File | Change |
|------|--------|
| `settings.py` | **New file** — `AuthSettings` with `SM_AUTH_` env prefix |
| `module.py` | Add `register_settings` override; update `register_middleware` to read from `app.state.auth_settings` |

## Hook Execution Order (final reference)

```
 Phase 1: Bootstrap
   1. Load framework Settings
   2. Discover & topological-sort modules
   3. Run diagnostics (dev only)

 Phase 2: App creation
   4. Create FastAPI app
   5. Store framework registries + settings on app.state

 Phase 3: Module settings
   6. register_settings(app)          — modules load their own config
   7. SM010 diagnostic check (dev only)

 Phase 4: Module registrations
   8. register_menu_items(registry)
   9. register_permissions(registry)
  10. register_feature_flags(registry)
  11. register_event_handlers(bus)
  12. register_health_checks(registry)

 Phase 5: Database
  13. init_db() → DatabaseState
  14. register_listeners(db_state)
  15. Store db_state on app.state

 Phase 6: App wiring
  16. Inertia setup
  17. register_exception_handlers(app)
  18. Middleware pipeline (register_middleware per module)
  19. register_routes(api_router, view_router)
  20. Mount health router
  21. Mount static files

 Phase 7: Runtime (async)
  22. on_startup(app)   — per module, in dependency order
  23. on_shutdown(app)   — per module, reverse order
```
