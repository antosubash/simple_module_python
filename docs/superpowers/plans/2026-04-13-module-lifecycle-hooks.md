# Module Lifecycle Hooks Implementation Plan

> **Note (2026-04-15):** Keycloak integration was removed; see plan
> `cryptic-juggling-lightning`. References to "Keycloak" below are
> historical context from the original design — the patterns still apply.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three new ModuleBase lifecycle hooks (register_exception_handlers, register_health_checks, register_settings), restructure the app boot sequence, add SM010 diagnostic, and migrate auth settings out of the framework.

**Architecture:** Each hook follows established patterns — registry-based (health) or direct app access (exception handlers, settings). The boot sequence moves app creation earlier so `app.state` is available for all hooks. A runtime SM010 diagnostic catches misconfigured settings hooks.

**Tech Stack:** Python 3.14, FastAPI, pydantic-settings, pytest, asyncio

---

### Task 1: Add HealthRegistry to simple_module_core

**Files:**
- Create: `framework/core/src/simple_module_core/health.py`
- Modify: `framework/core/src/simple_module_core/__init__.py:16-33`
- Test: `framework/core/tests/test_core.py`

- [ ] **Step 1: Write failing tests for HealthRegistry**

Add to the bottom of `framework/core/tests/test_core.py`:

```python
# ── HealthRegistry ─────────────────────────────────────────────────


from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus


class TestHealthRegistry:
    async def test_add_and_list(self):
        reg = HealthRegistry()

        async def check_db() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        reg.add(HealthCheck(name="db", check=check_db))
        assert len(reg.all_checks) == 1
        assert reg.all_checks[0].name == "db"

    async def test_empty_registry(self):
        reg = HealthRegistry()
        assert reg.all_checks == []

    async def test_multiple_checks(self):
        reg = HealthRegistry()

        async def check_a() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        async def check_b() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        reg.add(HealthCheck(name="a", check=check_a))
        reg.add(HealthCheck(name="b", check=check_b))
        assert len(reg.all_checks) == 2

    async def test_check_result_defaults(self):
        result = HealthCheckResult(status=HealthStatus.HEALTHY)
        assert result.detail is None

    async def test_check_result_with_detail(self):
        result = HealthCheckResult(status=HealthStatus.DEGRADED, detail="reindexing")
        assert result.detail == "reindexing"

    async def test_health_status_ordering(self):
        """Verify enum values exist for aggregation logic."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/core/tests/test_core.py::TestHealthRegistry -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create health.py module**

Create `framework/core/src/simple_module_core/health.py`:

```python
"""Health check registry for module-contributed health checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    status: HealthStatus
    detail: str | None = None


HealthCheckFn = Callable[[], Awaitable[HealthCheckResult]]


@dataclass
class HealthCheck:
    """A named health check with an async callable."""

    name: str
    check: HealthCheckFn


class HealthRegistry:
    """Collects health checks contributed by modules."""

    def __init__(self) -> None:
        self._checks: list[HealthCheck] = []

    def add(self, check: HealthCheck) -> None:
        self._checks.append(check)

    @property
    def all_checks(self) -> list[HealthCheck]:
        return list(self._checks)
```

- [ ] **Step 4: Add exports to `__init__.py`**

In `framework/core/src/simple_module_core/__init__.py`, add import and exports:

Add after the existing imports:
```python
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
```

Add to `__all__`:
```python
    "HealthCheck",
    "HealthCheckResult",
    "HealthRegistry",
    "HealthStatus",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/core/tests/test_core.py::TestHealthRegistry -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add framework/core/src/simple_module_core/health.py framework/core/src/simple_module_core/__init__.py framework/core/tests/test_core.py
git commit -m "feat: add HealthRegistry to simple_module_core"
```

---

### Task 2: Add three new hooks to ModuleBase

**Files:**
- Modify: `framework/core/src/simple_module_core/module.py:9-73`
- Test: `framework/core/tests/test_core.py`

- [ ] **Step 1: Write failing tests for new hooks**

Add to the bottom of `framework/core/tests/test_core.py`:

```python
class TestModuleNewHooks:
    async def test_register_exception_handlers_default_noop(self):
        mod = DummyModule()
        mod.register_exception_handlers(None)  # type: ignore

    async def test_register_health_checks_default_noop(self):
        mod = DummyModule()
        reg = HealthRegistry()
        mod.register_health_checks(reg)
        assert len(reg.all_checks) == 0

    async def test_register_settings_default_noop(self):
        mod = DummyModule()
        mod.register_settings(None)  # type: ignore
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/core/tests/test_core.py::TestModuleNewHooks -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add hooks to ModuleBase**

In `framework/core/src/simple_module_core/module.py`, add `HealthRegistry` to the TYPE_CHECKING imports:

```python
if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.permissions import PermissionRegistry
```

Replace the `ModuleBase` class docstring and add new hooks. The full class should become:

```python
class ModuleBase(ABC):
    """Base class for all modules.

    Subclasses override only the methods they need.
    Every method has a default no-op implementation.

    Hook execution order during app boot:

        Phase 1: Bootstrap
          - Load framework Settings
          - Discover & topological-sort modules
          - Run diagnostics (dev only)

        Phase 2: App creation
          - Create FastAPI app
          - Store framework registries + settings on app.state

        Phase 3: Module settings
          - register_settings(app)

        Phase 4: Module registrations
          - register_menu_items(registry)
          - register_permissions(registry)
          - register_feature_flags(registry)
          - register_event_handlers(bus)
          - register_health_checks(registry)

        Phase 5: Database
          - init_db() -> DatabaseState
          - register_listeners(db_state)

        Phase 6: App wiring
          - Inertia setup
          - register_exception_handlers(app)
          - Middleware pipeline (register_middleware per module)
          - register_routes(api_router, view_router)
          - Mount health router + static files

        Phase 7: Runtime (async)
          - on_startup(app) — per module, in dependency order
          - on_shutdown(app) — per module, reverse order
    """

    meta: ModuleMeta

    # ── Settings ─────────────────────────────────────────────

    def register_settings(self, app: FastAPI) -> None:
        """Load module-specific settings and store on ``app.state``.

        Called before all other registration hooks. Convention:
        store as ``app.state.<module_name_lower>_settings``.
        """

    # ── Service Registration ──────────────────────────────────

    def register_routes(
        self,
        api_router: APIRouter,
        view_router: APIRouter,
    ) -> None:
        """Register API endpoints and Inertia view routes."""

    def register_menu_items(self, registry: MenuRegistry) -> None:
        """Contribute menu items visible in the UI."""

    def register_permissions(self, registry: PermissionRegistry) -> None:
        """Declare permissions this module uses."""

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        """Declare feature flags this module exposes."""

    def register_event_handlers(self, bus: EventBus) -> None:
        """Subscribe to events published by other modules."""

    def register_health_checks(self, registry: HealthRegistry) -> None:
        """Contribute health checks for the ``/health/ready`` endpoint."""

    def register_middleware(self, app: FastAPI) -> None:
        """Add middleware to the application.

        Called after core middleware (session, security headers) positioning
        is established but before the app starts.  Modules that need to
        inject middleware (e.g. auth) override this method.
        """

    def register_exception_handlers(self, app: FastAPI) -> None:
        """Register custom exception handlers on the application.

        Called after framework exception handlers are set up.
        """

    # ── Lifecycle ─────────────────────────────────────────────

    async def on_startup(self, app: FastAPI) -> None:
        """Called after all modules are registered, during app startup."""

    async def on_shutdown(self, app: FastAPI) -> None:
        """Called during app shutdown."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/core/tests/test_core.py::TestModuleNewHooks -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add framework/core/src/simple_module_core/module.py framework/core/tests/test_core.py
git commit -m "feat: add register_settings, register_health_checks, register_exception_handlers hooks to ModuleBase"
```

---

### Task 3: Update diagnostics for new hooks

**Files:**
- Modify: `framework/core/src/simple_module_core/diagnostics.py:109-135`

- [ ] **Step 1: Add new hooks to `_check_empty_modules` method list**

In `framework/core/src/simple_module_core/diagnostics.py`, update the `_check_empty_modules` method. Replace the `for name in (...)` tuple to include all hooks:

```python
                for name in (
                    "register_routes",
                    "register_menu_items",
                    "register_permissions",
                    "register_feature_flags",
                    "register_event_handlers",
                    "register_middleware",
                    "register_health_checks",
                    "register_exception_handlers",
                    "register_settings",
                )
```

- [ ] **Step 2: Run existing diagnostics tests to verify nothing breaks**

Run: `uv run pytest framework/core/tests/test_core.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add framework/core/src/simple_module_core/diagnostics.py
git commit -m "chore: add new hooks to empty-module diagnostic check"
```

---

### Task 4: Create AuthSettings and register_settings hook

**Files:**
- Create: `modules/auth/src/sm_auth/settings.py`
- Modify: `modules/auth/src/sm_auth/module.py:1-49`
- Modify: `framework/hosting/src/simple_module_hosting/settings.py:1-31`
- Modify: `conftest.py:18-29`

- [ ] **Step 1: Create AuthSettings class**

Create `modules/auth/src/sm_auth/settings.py`:

```python
"""Auth module settings loaded from SM_AUTH_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Keycloak OAuth configuration for the auth module."""

    model_config = SettingsConfigDict(env_prefix="SM_AUTH_", env_file=".env", extra="ignore")

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "simple-module"
    keycloak_client_id: str = "simple-module-app"
    keycloak_client_secret: str = ""
```

- [ ] **Step 2: Add register_settings to AuthModule and update register_middleware**

Replace the full contents of `modules/auth/src/sm_auth/module.py`:

```python
"""Auth module definition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

if TYPE_CHECKING:
    from fastapi import FastAPI


class AuthModule(ModuleBase):
    meta = ModuleMeta(
        name="Auth",
        route_prefix="/auth",
    )

    def register_settings(self, app: FastAPI) -> None:
        from sm_auth.settings import AuthSettings

        app.state.auth_settings = AuthSettings()

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from sm_auth.endpoints.api import router as api

        api_router.include_router(api)

    def register_middleware(self, app: FastAPI) -> None:
        from sm_auth.middleware import AuthMiddleware
        from sm_auth.oauth import configure_oauth

        settings = app.state.auth_settings
        configure_oauth(
            keycloak_url=settings.keycloak_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
        )
        app.add_middleware(AuthMiddleware)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Logout",
                url="/auth/logout",
                icon="log-out",
                order=999,
                section=MenuSection.USER_DROPDOWN,
            )
        )
```

- [ ] **Step 3: Remove keycloak fields from framework Settings**

In `framework/hosting/src/simple_module_hosting/settings.py`, remove the keycloak fields. The file should become:

```python
"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the SimpleModule host application.

    All settings can be overridden via environment variables prefixed with ``SM_``.
    """

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # App
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    vite_dev_url: str = "http://localhost:5173"
    debug: bool = False

    @property
    def is_development(self) -> bool:
        return self.environment == "development"
```

- [ ] **Step 4: Update conftest.py to remove keycloak fields from Settings fixture**

In `conftest.py`, update the `settings` fixture. Remove the `keycloak_*` kwargs:

```python
@pytest.fixture
def settings() -> Settings:
    """Settings configured for testing with in-memory SQLite."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment="testing",
        secret_key="test-secret-key",
    )
```

- [ ] **Step 5: Run tests to check for breakage**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests PASS (auth module will create its own AuthSettings from env/defaults)

- [ ] **Step 6: Commit**

```bash
git add modules/auth/src/sm_auth/settings.py modules/auth/src/sm_auth/module.py framework/hosting/src/simple_module_hosting/settings.py conftest.py
git commit -m "feat: move keycloak settings from framework to AuthModule via register_settings hook"
```

---

### Task 5: Restructure app_builder.py boot sequence

**Files:**
- Modify: `framework/hosting/src/simple_module_hosting/app_builder.py:1-197`

- [ ] **Step 1: Rewrite create_app with new boot order**

Replace the entire `create_app` function in `framework/hosting/src/simple_module_hosting/app_builder.py`. The imports and `_setup_inertia` function remain unchanged. Replace only `create_app`:

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the full FastAPI application.

    Boot sequence:
      1. Load settings & discover modules
      2. Run diagnostics (dev only)
      3. Create FastAPI app & store framework state
      4. Module settings (register_settings)
      5. Module registrations (menu, permissions, flags, events, health)
      6. Initialize database
      7. Inertia setup & exception handlers (register_exception_handlers)
      8. Middleware pipeline (register_middleware)
      9. Routes (register_routes), health endpoints, static files
    """
    settings = settings or Settings()

    # ── Phase 1: Discover modules ──────────────────────────
    modules = discover_modules()
    modules = topological_sort(modules)
    logger.info(
        "Loaded %d module(s): %s",
        len(modules),
        ", ".join(m.meta.name for m in modules),
    )

    # ── Phase 2: Run diagnostics (dev only) ────────────────
    if settings.is_development:
        diagnostics = run_diagnostics(modules)
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")

    # ── Phase 3: Create FastAPI app ────────────────────────
    menu_registry = MenuRegistry()
    perm_registry = PermissionRegistry()
    ff_registry = FeatureFlagRegistry()
    event_bus = EventBus()
    health_registry = HealthRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)

    app = FastAPI(
        title="SimpleModule",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    app.state.menu_registry = menu_registry
    app.state.perm_registry = perm_registry
    app.state.ff_registry = ff_registry
    app.state.event_bus = event_bus
    app.state.health_registry = health_registry
    app.state.settings = settings

    # ── Phase 4: Module settings ───────────────────────────
    for mod in modules:
        mod.register_settings(app)

    # SM010: warn if register_settings was overridden but added nothing
    if settings.is_development:
        _check_settings_registration(modules, app)

    # ── Phase 5: Module registrations ──────────────────────
    for mod in modules:
        mod.register_menu_items(menu_registry)
        mod.register_permissions(perm_registry)
        mod.register_feature_flags(ff_registry)
        mod.register_event_handlers(event_bus)
        mod.register_health_checks(health_registry)

    logger.info(
        "Registered %d menu items, %d permissions, %d feature flags, %d health checks",
        len(menu_registry.all_items),
        len(perm_registry.all_permissions),
        len(ff_registry.all_flags),
        len(health_registry.all_checks),
    )

    # ── Phase 6: Initialize database ───────────────────────
    db_state = init_db(settings.database_url, echo=settings.debug)
    register_listeners(db_state)
    app.state.db = db_state

    # ── Phase 7: Inertia + exception handlers ──────────────
    _setup_inertia(app, settings)

    app.add_exception_handler(
        InertiaVersionConflictException,
        inertia_version_conflict_exception_handler,  # ty: ignore[invalid-argument-type]
    )
    for mod in modules:
        mod.register_exception_handlers(app)

    # ── Phase 8: Middleware pipeline ───────────────────────
    # Order matters: last added = first executed
    # Execution order: SecurityHeaders → Session → [module middleware] → InertiaLayout
    app.add_middleware(
        InertiaLayoutDataMiddleware,
        menu_registry=menu_registry,
        permission_registry=perm_registry,
    )
    for mod in modules:
        mod.register_middleware(app)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
    app.add_middleware(SecurityHeadersMiddleware)

    # ── Phase 9: Routes, health, static files ──────────────
    for mod in modules:
        api_router = APIRouter(
            prefix=mod.meta.route_prefix,
            tags=[mod.meta.name],
        )
        view_router = APIRouter(
            prefix=mod.meta.view_prefix,
            tags=[f"{mod.meta.name} Views"],
        )
        mod.register_routes(api_router, view_router)
        app.include_router(api_router)
        app.include_router(view_router)

    app.include_router(health_router)

    import os

    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "host", "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


def _check_settings_registration(modules: list, app: FastAPI) -> None:
    """SM010: warn if a module overrides register_settings but added nothing to app.state."""
    from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel

    # Snapshot known framework keys on app.state
    framework_keys = {
        "menu_registry", "perm_registry", "ff_registry",
        "event_bus", "health_registry", "settings",
    }
    state_keys = {k for k in vars(app.state) if not k.startswith("_")}
    module_added_keys = state_keys - framework_keys

    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        # Check if any key looks like it belongs to this module
        mod_prefix = mod.meta.name.lower()
        has_key = any(mod_prefix in k for k in module_added_keys)
        if not has_key:
            diag = Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM010",
                message="register_settings() was overridden but added nothing to app.state",
                module_name=mod.meta.name,
                suggestion=(
                    f"Store your settings on app.state "
                    f"(e.g., app.state.{mod_prefix}_settings = {mod.meta.name}Settings())"
                ),
            )
            print(str(diag))
            print()
```

- [ ] **Step 2: Add HealthRegistry import to app_builder.py**

Add to the existing imports at the top of `app_builder.py`:

```python
from simple_module_core.health import HealthRegistry
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add framework/hosting/src/simple_module_hosting/app_builder.py
git commit -m "refactor: restructure create_app boot sequence with new hook phases and SM010 diagnostic"
```

---

### Task 6: Update health.py to use HealthRegistry

**Files:**
- Modify: `framework/hosting/src/simple_module_hosting/health.py:1-21`
- Test: `framework/hosting/tests/test_app.py`

- [ ] **Step 1: Write failing test for module-contributed health checks**

Add to the bottom of `framework/hosting/tests/test_app.py`:

```python
class TestHealthReady:
    async def test_ready_includes_module_checks(self, app: FastAPI, client: httpx.AsyncClient):
        """If modules registered health checks, /health/ready should include them."""
        from simple_module_core.health import (
            HealthCheck,
            HealthCheckResult,
            HealthRegistry,
            HealthStatus,
        )

        # Add a test health check to the registry
        registry: HealthRegistry = app.state.health_registry

        async def check_test_service() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        registry.add(HealthCheck(name="test_service", check=check_test_service))

        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data
        assert data["checks"]["test_service"]["status"] == "healthy"

    async def test_ready_degraded_status(self, app: FastAPI, client: httpx.AsyncClient):
        from simple_module_core.health import (
            HealthCheck,
            HealthCheckResult,
            HealthRegistry,
            HealthStatus,
        )

        registry: HealthRegistry = app.state.health_registry

        async def check_degraded() -> HealthCheckResult:
            return HealthCheckResult(status=HealthStatus.DEGRADED, detail="slow")

        registry.add(HealthCheck(name="slow_service", check=check_degraded))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["slow_service"]["detail"] == "slow"

    async def test_ready_unhealthy_on_exception(self, app: FastAPI, client: httpx.AsyncClient):
        from simple_module_core.health import HealthCheck, HealthRegistry

        registry: HealthRegistry = app.state.health_registry

        async def check_broken():
            raise ConnectionError("connection refused")

        registry.add(HealthCheck(name="broken_service", check=check_broken))

        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["broken_service"]["status"] == "unhealthy"
        assert "connection refused" in data["checks"]["broken_service"]["detail"]

    async def test_ready_no_checks_is_healthy(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_app.py::TestHealthReady -v`
Expected: FAIL (current /health/ready returns `{"status": "ready"}` with no `checks` key)

- [ ] **Step 3: Rewrite health.py to use HealthRegistry**

Replace `framework/hosting/src/simple_module_hosting/health.py`:

```python
"""Health check endpoints."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from simple_module_core.health import HealthCheckResult, HealthRegistry, HealthStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Severity ordering for aggregation: worst status wins
_STATUS_SEVERITY = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.DEGRADED: 1,
    HealthStatus.UNHEALTHY: 2,
}


@router.get("/health")
async def health() -> dict:
    return {"status": "healthy"}


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request) -> dict:
    registry: HealthRegistry = request.app.state.health_registry
    checks = registry.all_checks

    if not checks:
        return {"status": "healthy", "checks": {}}

    # Run all checks concurrently
    results: dict[str, HealthCheckResult] = {}
    async def _run_check(name: str, check_fn):
        try:
            return name, await check_fn()
        except Exception as exc:
            return name, HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                detail=str(exc),
            )

    tasks = [_run_check(c.name, c.check) for c in checks]
    completed = await asyncio.gather(*tasks)

    for name, result in completed:
        results[name] = result

    # Aggregate: worst status wins
    worst = HealthStatus.HEALTHY
    for result in results.values():
        if _STATUS_SEVERITY[result.status] > _STATUS_SEVERITY[worst]:
            worst = result.status

    return {
        "status": worst.value,
        "checks": {
            name: {"status": r.status.value, **({"detail": r.detail} if r.detail else {})}
            for name, r in results.items()
        },
    }
```

- [ ] **Step 4: Update existing health ready test**

In `framework/hosting/tests/test_app.py`, update the existing `test_health_ready` test in `TestHealthEndpoints` to match the new response shape:

```python
    async def test_health_ready(self, client: httpx.AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "checks" in data
```

- [ ] **Step 5: Run all tests**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/src/simple_module_hosting/health.py framework/hosting/tests/test_app.py
git commit -m "feat: update /health/ready to aggregate module-contributed health checks"
```

---

### Task 7: Verify app.state.health_registry in integration test

**Files:**
- Test: `framework/hosting/tests/test_app.py`

- [ ] **Step 1: Add test for health_registry on app.state**

Add to `TestCreateApp` in `framework/hosting/tests/test_app.py`:

```python
    async def test_app_state_has_health_registry(self, app: FastAPI):
        assert hasattr(app.state, "health_registry")
```

- [ ] **Step 2: Run test**

Run: `uv run pytest framework/hosting/tests/test_app.py::TestCreateApp::test_app_state_has_health_registry -v`
Expected: PASS

- [ ] **Step 3: Add test for app.state.db (fixes bug from restructure)**

Add to `TestCreateApp`:

```python
    async def test_app_state_has_db(self, app: FastAPI):
        from simple_module_db.session import DatabaseState

        assert hasattr(app.state, "db")
        assert isinstance(app.state.db, DatabaseState)
```

- [ ] **Step 4: Run test**

Run: `uv run pytest framework/hosting/tests/test_app.py::TestCreateApp::test_app_state_has_db -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/tests/test_app.py
git commit -m "test: verify health_registry and db on app.state"
```

---

### Task 8: Run full test suite and fix any breakage

**Files:**
- Any files that need fixes

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Fix any failures**

If tests fail, diagnose and fix. Common issues:
- `conftest.py` `app` fixture may reference `get_engine()` which was a global — needs updating to use `app.state.db.engine` instead
- Auth tests may expect keycloak fields on `Settings`

- [ ] **Step 3: Run ruff linter**

Run: `uv run ruff check framework/ modules/ conftest.py`
Expected: No errors

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve test breakage from boot sequence restructure"
```

---

### Task 9: Final integration smoke test

- [ ] **Step 1: Run the complete test suite one final time**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS, zero failures

- [ ] **Step 2: Verify SM009 still catches coupling violations**

Quick sanity check — temporarily add a bad import to `app_builder.py` and verify the diagnostic catches it. Then revert.

Run:
```bash
python -c "
from simple_module_core.diagnostics import ModuleDiagnostics
from simple_module_core.discovery import discover_modules
diags = ModuleDiagnostics().run(discover_modules())
sm009 = [d for d in diags if d.code == 'SM009']
print(f'SM009 violations: {len(sm009)}')
for d in sm009:
    print(d)
if not sm009:
    print('No framework-module coupling detected (clean)')
"
```
Expected: `No framework-module coupling detected (clean)`

- [ ] **Step 3: Commit and done**

No commit needed unless fixes were made. The feature is complete.
