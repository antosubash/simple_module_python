# App state organization — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 15+ loose attributes on `app.state` with one typed slot per owner: framework gets `app.state.sm: Services` (a frozen dataclass), each module with state gets `app.state.<module>: <Module>Services`. Drop three duplicate locale fields and the runtime drift-detection block.

**Architecture:** Two-stage rollout per owner: (1) introduce the new slot alongside existing loose keys, (2) migrate consumers to read the new slot, (3) delete the old keys. Each stage is an independent commit that keeps the tree green. Storage stays on `app.state` — only its shape changes.

**Tech Stack:** Python 3.12, FastAPI/Starlette `app.state`, `dataclasses` (frozen + slots), pytest, ty (static type checker).

**Spec:** `docs/superpowers/specs/2026-04-17-app-state-organization-design.md`

---

## Glossary (used in steps below)

- **Framework loose keys** → moving onto `app.state.sm`: `modules`, `menu_registry`, `perm_registry`, `ff_registry`, `event_bus`, `health_registry`, `settings`, `i18n_registry`, `db`, `inertia_config`.
- **Framework loose keys** → *staying* loose: `inertia_dependency` (fastapi-inertia request-scoped factory), `migration` (dev boot warning, lifespan-set).
- **Duplicate locale keys** → deleting: `settings_default_locale`, `settings_supported_locales`, `settings_cookie_name` — read `settings.i18n_*` directly.
- **Users module keys** → moving onto `app.state.users: UsersServices`: `users_settings`, `mailer`, `rate_limiter`, `auth_throughput_limiter`, `users_roles_cache`.
- No other modules today set loose `app.state` entries. `AuthModule` has no state.

## Verification commands (referenced by tasks)

- `make lint` — Ruff + ty + Biome + tsc.
- `make test` — full pytest suite.
- `uv run pytest <path>` — single-file/test runs.

Engineers running in the worktree `/Volumes/ext1/Sandbox/simple_module_python/flamboyant-ardinghelli-753294/` should run commands from that directory.

---

## Phase 1 — Foundation

### Task 1: Create the `Services` dataclass

**Files:**
- Create: `framework/core/simple_module_core/services.py`
- Create: `framework/core/tests/test_services.py`
- Modify: `framework/core/simple_module_core/__init__.py` (add export)

- [ ] **Step 1: Write the failing test**

Create `framework/core/tests/test_services.py`:

```python
"""Services dataclass — framework-scoped singleton container."""

from __future__ import annotations

import pytest

from simple_module_core.services import Services


def test_services_is_frozen() -> None:
    """Mutation after construction must raise — singletons don't change at runtime."""
    s = _make_services()
    with pytest.raises((AttributeError, TypeError)):
        s.settings = None  # type: ignore[misc]


def test_services_has_slots() -> None:
    """Slotted dataclass prevents silent attribute additions (the original bloat pattern)."""
    s = _make_services()
    with pytest.raises(AttributeError):
        s.rogue_new_attribute = 42  # type: ignore[attr-defined]


def test_services_round_trip_field_access() -> None:
    """Every declared field must be readable after construction."""
    s = _make_services()
    assert s.settings is _SENTINEL_SETTINGS
    assert s.db is _SENTINEL_DB
    assert s.event_bus is _SENTINEL_EVENT_BUS
    assert s.menu_registry is _SENTINEL_MENU
    assert s.permissions is _SENTINEL_PERMS
    assert s.feature_flags is _SENTINEL_FLAGS
    assert s.health_registry is _SENTINEL_HEALTH
    assert s.i18n_registry is _SENTINEL_I18N
    assert s.inertia_config is _SENTINEL_INERTIA
    assert s.modules == ()


_SENTINEL_SETTINGS = object()
_SENTINEL_DB = object()
_SENTINEL_EVENT_BUS = object()
_SENTINEL_MENU = object()
_SENTINEL_PERMS = object()
_SENTINEL_FLAGS = object()
_SENTINEL_HEALTH = object()
_SENTINEL_I18N = object()
_SENTINEL_INERTIA = object()


def _make_services() -> Services:
    # Fields are typed but at runtime we can pass sentinels; typing lives
    # in production call-sites, not these structural tests.
    return Services(
        settings=_SENTINEL_SETTINGS,  # type: ignore[arg-type]
        db=_SENTINEL_DB,  # type: ignore[arg-type]
        event_bus=_SENTINEL_EVENT_BUS,  # type: ignore[arg-type]
        menu_registry=_SENTINEL_MENU,  # type: ignore[arg-type]
        permissions=_SENTINEL_PERMS,  # type: ignore[arg-type]
        feature_flags=_SENTINEL_FLAGS,  # type: ignore[arg-type]
        health_registry=_SENTINEL_HEALTH,  # type: ignore[arg-type]
        i18n_registry=_SENTINEL_I18N,  # type: ignore[arg-type]
        inertia_config=_SENTINEL_INERTIA,  # type: ignore[arg-type]
        modules=(),
    )
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest framework/core/tests/test_services.py -v
```

Expected: `ModuleNotFoundError: No module named 'simple_module_core.services'`.

- [ ] **Step 3: Implement `services.py`**

Create `framework/core/simple_module_core/services.py`:

```python
"""Framework-scoped singleton container.

Stored as ``app.state.sm`` during :func:`create_app`. Consumers read
``request.app.state.sm.<field>`` instead of reaching for loose
``app.state`` attributes — gives us typing, discoverability, and a
single place to see what the framework owns.

Frozen + slotted by design: Services is built once at boot and never
mutated. Slots reject attribute additions, which is how the previous
``app.state`` shape grew unbounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inertia import InertiaConfig
    from simple_module_core.events import EventBus
    from simple_module_core.feature_flags import FeatureFlagRegistry
    from simple_module_core.health import HealthRegistry
    from simple_module_core.i18n import I18nRegistry
    from simple_module_core.menu import MenuRegistry
    from simple_module_core.module import ModuleBase
    from simple_module_core.permissions import PermissionRegistry
    from simple_module_db.session import DatabaseState
    from simple_module_hosting.settings import Settings


@dataclass(frozen=True, slots=True)
class Services:
    """Framework singletons. One slot per owner, read-only after boot."""

    settings: Settings
    db: DatabaseState
    event_bus: EventBus
    menu_registry: MenuRegistry
    permissions: PermissionRegistry
    feature_flags: FeatureFlagRegistry
    health_registry: HealthRegistry
    i18n_registry: I18nRegistry
    inertia_config: InertiaConfig
    modules: tuple[ModuleBase, ...]
```

- [ ] **Step 4: Export from the package**

Modify `framework/core/simple_module_core/__init__.py`: add the following import near the other registry imports (alphabetical within the block is fine), and add `"Services"` to `__all__` in its sorted position.

```python
from simple_module_core.services import Services
```

The existing `__all__` list already sorts alphabetically — slot `"Services"` between `"PermissionRegistry"` and `"Translator"`.

- [ ] **Step 5: Run the test to confirm it passes**

```bash
uv run pytest framework/core/tests/test_services.py -v
```

Expected: all three tests pass.

- [ ] **Step 6: Confirm the existing suite still passes**

```bash
uv run pytest framework/core/tests -x
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add framework/core/simple_module_core/services.py framework/core/simple_module_core/__init__.py framework/core/tests/test_services.py
git commit -m "feat(core): add Services dataclass for framework singletons"
```

---

### Task 2: Populate `app.state.sm` in `create_app` alongside existing writes

Build `Services` at the end of `create_app` when every field has been set. Loose keys remain written; nothing is removed yet so consumers keep working.

**Files:**
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`
- Modify: `framework/hosting/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Append to `framework/hosting/tests/test_app.py` (read the file first to match the existing fixture style):

```python
def test_app_state_has_sm_services(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """create_app populates app.state.sm with a Services instance."""
    from simple_module_core.services import Services

    monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "host" / "templates").mkdir(parents=True)
    (tmp_path / "host" / "templates" / "index.html").write_text("<html></html>")

    app = create_app()

    sm = app.state.sm
    assert isinstance(sm, Services)
    # Fields resolve to the same instances still on loose keys (both coexist
    # during the staged rollout).
    assert sm.settings is app.state.settings
    assert sm.db is app.state.db
    assert sm.event_bus is app.state.event_bus
    assert sm.menu_registry is app.state.menu_registry
    assert sm.permissions is app.state.perm_registry
    assert sm.feature_flags is app.state.ff_registry
    assert sm.health_registry is app.state.health_registry
    assert sm.i18n_registry is app.state.i18n_registry
    assert sm.inertia_config is app.state.inertia_config
    assert sm.modules == tuple(app.state.modules)
```

Also add `import pytest` at the top if not present.

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest framework/hosting/tests/test_app.py::test_app_state_has_sm_services -v
```

Expected: FAIL with `AttributeError: ... no attribute 'sm'`.

- [ ] **Step 3: Populate `app.state.sm` at the end of `create_app`**

In `framework/hosting/simple_module_hosting/app_builder.py`, add the import near the other `simple_module_core` imports:

```python
from simple_module_core.services import Services
```

Then, immediately before `return app` at the bottom of `create_app` (currently line 232), insert:

```python
    # Typed singleton container. Loose app.state.* keys remain for the
    # duration of the staged migration; consumers read from app.state.sm.*.
    app.state.sm = Services(
        settings=settings,
        db=db_state,
        event_bus=event_bus,
        menu_registry=menu_registry,
        permissions=perm_registry,
        feature_flags=ff_registry,
        health_registry=health_registry,
        i18n_registry=i18n_registry,
        inertia_config=app.state.inertia_config,
        modules=tuple(modules),
    )
```

- [ ] **Step 4: Run the new test**

```bash
uv run pytest framework/hosting/tests/test_app.py::test_app_state_has_sm_services -v
```

Expected: PASS.

- [ ] **Step 5: Run the hosting suite**

```bash
uv run pytest framework/hosting/tests -x
```

Expected: all green (nothing downstream reads `sm` yet).

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/app_builder.py framework/hosting/tests/test_app.py
git commit -m "feat(hosting): populate app.state.sm alongside loose keys"
```

---

## Phase 2 — Migrate framework consumers

After this phase, every framework-internal read of framework-owned state goes through `app.state.sm.*`. Loose keys are still written (deleted in Phase 4).

### Task 3: Migrate error-handlers, health, inertia setup

**Files:**
- Modify: `framework/hosting/simple_module_hosting/_error_handlers.py`
- Modify: `framework/hosting/simple_module_hosting/health.py`
- Modify: `framework/hosting/simple_module_hosting/_inertia_setup.py`

- [ ] **Step 1: Update `_error_handlers.py`**

Line 25 currently:

```python
    config: InertiaConfig = request.app.state.inertia_config
```

Replace with:

```python
    config: InertiaConfig = request.app.state.sm.inertia_config
```

- [ ] **Step 2: Update `health.py`**

Line 39 currently:

```python
    registry: HealthRegistry = request.app.state.health_registry
```

Replace with:

```python
    registry: HealthRegistry = request.app.state.sm.health_registry
```

(Line 25 `getattr(request.app.state, "migration", None)` stays — `migration` stays loose.)

- [ ] **Step 3: `_inertia_setup.py` — no read changes**

This file writes `app.state.inertia_config` and `app.state.inertia_dependency`. Both writes stay as-is — they happen during boot and are consumed by the `Services` constructor (for `inertia_config`) and by `inertia_deps.py` at request time (for `inertia_dependency`).

No change required to `_inertia_setup.py` in this task.

- [ ] **Step 4: Migrate the lifespan block's `app.state.db` reads**

In `framework/hosting/simple_module_hosting/app_builder.py`, the `lifespan` function (currently lines 142-151) reads `app.state.db.engine` twice. Update both to read via `app.state.sm.db.engine` so Task 10's deletion of the loose `app.state.db` key doesn't break startup/shutdown.

Before:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.db.engine)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()
```

After:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.sm.db.engine)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()
```

`app.state.sm` is populated at the end of `create_app` (Task 2), before FastAPI invokes the lifespan, so `sm.db` is always resolvable here.

- [ ] **Step 5: Run the hosting suite**

```bash
uv run pytest framework/hosting/tests -x
```

Expected: all green. The health test and any Inertia error-page test should still pass — `app.state.sm.inertia_config` is a live alias to the same object.

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/_error_handlers.py framework/hosting/simple_module_hosting/health.py framework/hosting/simple_module_hosting/app_builder.py
git commit -m "refactor(hosting): read framework singletons via app.state.sm"
```

---

### Task 4: Migrate `inertia_deps`, `i18n_deps`, `permissions`

**Files:**
- Modify: `framework/hosting/simple_module_hosting/inertia_deps.py`
- Modify: `framework/hosting/simple_module_hosting/i18n_deps.py`
- Modify: `framework/hosting/simple_module_hosting/permissions.py`

- [ ] **Step 1: `inertia_deps.py` — keep loose read of `inertia_dependency`**

Line 17 currently:

```python
    inertia_dep = request.app.state.inertia_dependency
```

No change — `inertia_dependency` is intentionally left loose (it's a `Depends` factory, not a singleton owned by `Services`). Keep the read as-is.

- [ ] **Step 2: `i18n_deps.py` — migrate both reads**

Lines 20-21 currently:

```python
    registry = request.app.state.i18n_registry
    default_locale = request.app.state.settings_default_locale
```

Replace with:

```python
    registry = request.app.state.sm.i18n_registry
    default_locale = request.app.state.sm.settings.i18n_default_locale
```

Also update the docstring on lines 13-18 to reflect the new sources:

```python
    """Resolve a Translator bound to ``request.state.locale``.

    Reads the registry from ``request.app.state.sm.i18n_registry`` and the
    default locale from ``request.app.state.sm.settings.i18n_default_locale``.

    ``request.state.locale`` is populated by LocaleMiddleware.
    """
```

- [ ] **Step 3: `permissions.py` — migrate the fallback read**

Line 62 currently:

```python
            perm_registry = getattr(getattr(request.app, "state", None), "perm_registry", None)
```

Replace with:

```python
            sm = getattr(getattr(request.app, "state", None), "sm", None)
            perm_registry = getattr(sm, "permissions", None) if sm is not None else None
```

The surrounding `if ... is not None` handling is unchanged.

- [ ] **Step 4: Run the hosting + core suites**

```bash
uv run pytest framework/hosting/tests framework/core/tests -x
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/i18n_deps.py framework/hosting/simple_module_hosting/permissions.py
git commit -m "refactor(hosting): read i18n + permission singletons via app.state.sm"
```

---

### Task 5: Migrate `host/routes_i18n.py` and its tests

**Files:**
- Modify: `host/routes_i18n.py`
- Modify: `host/tests/test_routes_i18n.py`

- [ ] **Step 1: Update the endpoint to read from `settings` directly**

`host/routes_i18n.py` lines 27-33 currently:

```python
    registry = getattr(request.app.state, "i18n_registry", None)
    if registry is not None:
        supported = registry.available_locales()
    else:
        # Fallback for tests that build a minimal app without the registry.
        supported = request.app.state.settings_supported_locales
    cookie_name: str = request.app.state.settings_cookie_name
```

Replace with:

```python
    sm = getattr(request.app.state, "sm", None)
    if sm is not None:
        supported = sm.i18n_registry.available_locales()
        cookie_name: str = sm.settings.i18n_cookie_name
    else:
        # Fallback for tests that build a minimal app without Services.
        supported = request.app.state.settings_supported_locales
        cookie_name = request.app.state.settings_cookie_name
```

Both branches are retained during migration — the minimal-app test path (Task 5 Step 2 below) still writes the loose keys. Deletion of the duplicates happens in Task 11.

- [ ] **Step 2: Verify the test still passes with no code change**

The test fixture on `host/tests/test_routes_i18n.py:13-14` writes the loose fallback keys:

```python
    app.state.settings_supported_locales = supported
    app.state.settings_cookie_name = "locale"
```

Leave those unchanged for now — they feed the fallback branch. They get rewritten in Task 11.

Run:

```bash
uv run pytest host/tests/test_routes_i18n.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add host/routes_i18n.py
git commit -m "refactor(host): read i18n state via app.state.sm with fallback"
```

---

### Task 6: Migrate cross-boundary module reads of framework state

Three module files read framework-owned state directly from `app.state`. Migrate them to `app.state.sm.*` so they don't block framework cleanup in Phase 4.

**Files:**
- Modify: `modules/auth/auth/deps.py`
- Modify: `modules/users/users/middleware.py`
- Modify: `modules/users/users/endpoints/views.py`

- [ ] **Step 1: `modules/auth/auth/deps.py` — migrate `perm_registry` read**

Line 46 currently:

```python
        perm_registry = request.app.state.perm_registry
```

Replace with:

```python
        perm_registry = request.app.state.sm.permissions
```

- [ ] **Step 2: `modules/users/users/middleware.py` — migrate `db` read**

Line 120 currently (inside the docstring text is fine; the code around it is what matters). Search for `app.state.db.session_factory` in the file; replace that usage to read via `sm`:

```python
        async with request.app.state.sm.db.session_factory() as db:
```

(Replace `request.app.state.db` wherever it appears in the module's middleware. The `from __future__ import annotations` import list does not need changes.)

- [ ] **Step 3: `modules/users/users/endpoints/views.py` — migrate the `settings` read**

Line 30 currently:

```python
    if request.app.state.settings.is_development:
```

Replace with:

```python
    if request.app.state.sm.settings.is_development:
```

(Other reads in this file — `users_settings`, `users_settings.cookie_name`, etc. — move in Task 8.)

- [ ] **Step 4: Run the affected module tests**

```bash
uv run pytest modules/auth/tests modules/users/tests -x
```

Expected: all green. Tests that assemble mock requests still work because they populate `app.state` the same way `create_app` does (framework first, then migrate them in Task 9).

If a test fails because its mock request lacks `.sm`, fix it inline by adding a minimal `Services`-like namespace or by switching the mock to use the new attribute. Pattern:

```python
request.app.state.sm = SimpleNamespace(permissions=perm_registry_instance)
```

- [ ] **Step 5: Commit**

```bash
git add modules/auth/auth/deps.py modules/users/users/middleware.py modules/users/users/endpoints/views.py
git commit -m "refactor(modules): read framework state via app.state.sm"
```

---

## Phase 3 — Users module migration

### Task 7: Create `UsersServices` + populate in `UsersModule`

**Files:**
- Create: `modules/users/users/services.py`
- Modify: `modules/users/users/module.py`

- [ ] **Step 1: Write the services module**

Create `modules/users/users/services.py`:

```python
"""Module-scoped state container for the users module.

Stored as ``app.state.users`` by :meth:`UsersModule.register_settings` (for
fields available at that phase) and populated the rest of the way during
:meth:`UsersModule.on_startup` (for fields that depend on the DB or other
framework services).

Not frozen — ``on_startup`` needs to set fields that aren't available at
``register_settings`` time. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from users.mailer import Mailer
    from users.rate_limit import LoginRateLimiter, ThroughputLimiter
    from users.roles_cache import RoleSummary
    from users.settings import UsersSettings


@dataclass
class UsersServices:
    """Users-module singletons. Single slot at ``app.state.users``."""

    settings: UsersSettings
    mailer: Mailer | None = None
    rate_limiter: LoginRateLimiter | None = None
    auth_throughput_limiter: ThroughputLimiter | None = None
    roles_cache: list[RoleSummary] = field(default_factory=list)
```

- [ ] **Step 2: Update `UsersModule.register_settings` and `on_startup`**

In `modules/users/users/module.py`, replace `register_settings` (lines 24-27):

```python
    def register_settings(self, app: FastAPI) -> None:
        from users.services import UsersServices
        from users.settings import UsersSettings

        services = UsersServices(settings=UsersSettings())
        app.state.users = services
        app.state.users_settings = services.settings  # deprecated loose alias, removed Phase 4
```

Replace `on_startup` (lines 84-114) — keep the existing behaviour, populate `services` fields instead of loose keys:

```python
    async def on_startup(self, app: FastAPI) -> None:
        """Build the mailer, rate limiter, and apply production cookie params."""
        import asyncio

        from users.backend import reconfigure_cookie_transport
        from users.bootstrap import bootstrap_admin_from_env
        from users.deps import auth_backend
        from users.mailer import build_mailer
        from users.rate_limit import LoginRateLimiter, ThroughputLimiter
        from users.roles_cache import refresh_roles_cache

        services = app.state.users
        s = services.settings
        services.mailer = build_mailer(s)
        services.rate_limiter = LoginRateLimiter(
            max_failures=s.login_rate_limit_failures,
            window_seconds=s.login_rate_limit_window_seconds,
            cooldown_seconds=s.login_rate_limit_cooldown_seconds,
        )
        services.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=s.auth_rate_limit_attempts,
            window_seconds=s.auth_rate_limit_window_seconds,
        )
        # Deprecated loose aliases — removed Phase 4.
        app.state.mailer = services.mailer
        app.state.rate_limiter = services.rate_limiter
        app.state.auth_throughput_limiter = services.auth_throughput_limiter

        reconfigure_cookie_transport(auth_backend, s)

        await asyncio.gather(
            bootstrap_admin_from_env(app),
            refresh_roles_cache(app),
        )
```

The "deprecated loose aliases" block keeps the old keys in sync with `services.*` while consumers migrate. Removed in Task 10's cleanup step.

- [ ] **Step 3: Run the users test suite**

```bash
uv run pytest modules/users/tests -x
```

Expected: all green. The test suite reads `app.state.users_settings` etc., which still resolves via the deprecated aliases.

- [ ] **Step 4: Commit**

```bash
git add modules/users/users/services.py modules/users/users/module.py
git commit -m "feat(users): introduce UsersServices at app.state.users"
```

---

### Task 8: Migrate users-module consumers

Rewrite every `request.app.state.<loose key>` read inside the users module to `request.app.state.users.<field>`.

**Files:**
- Modify: `modules/users/users/manager.py`
- Modify: `modules/users/users/deps.py`
- Modify: `modules/users/users/endpoints/api.py`
- Modify: `modules/users/users/endpoints/api_admin.py`
- Modify: `modules/users/users/endpoints/views.py`
- Modify: `modules/users/users/roles_cache.py`

- [ ] **Step 1: `manager.py`**

Lines 128-129 currently:

```python
    mailer = request.app.state.mailer
    settings = request.app.state.users_settings
```

Replace with:

```python
    users = request.app.state.users
    mailer = users.mailer
    settings = users.settings
```

- [ ] **Step 2: `deps.py` — `get_mailer` and `get_event_bus`**

Lines 51-58 currently:

```python
def get_mailer(request: Request):
    """Return the mailer from app.state (built in UsersModule.on_startup)."""
    return request.app.state.mailer


def get_event_bus(request: Request) -> EventBus:
    """Return the event bus from app.state."""
    return request.app.state.event_bus
```

Replace with:

```python
def get_mailer(request: Request):
    """Return the mailer from app.state.users (built in UsersModule.on_startup)."""
    return request.app.state.users.mailer


def get_event_bus(request: Request) -> EventBus:
    """Return the event bus from app.state.sm."""
    return request.app.state.sm.event_bus
```

- [ ] **Step 3: `endpoints/api.py` — rate limiter helpers**

Lines 42-44 currently:

```python
def get_rate_limiter(request: Request) -> LoginRateLimiter:
    """Return the per-app LoginRateLimiter built in UsersModule.on_startup."""
    return request.app.state.rate_limiter
```

Replace with:

```python
def get_rate_limiter(request: Request) -> LoginRateLimiter:
    """Return the per-app LoginRateLimiter built in UsersModule.on_startup."""
    return request.app.state.users.rate_limiter
```

Line 58 currently:

```python
    limiter: ThroughputLimiter = request.app.state.auth_throughput_limiter
```

Replace with:

```python
    limiter: ThroughputLimiter = request.app.state.users.auth_throughput_limiter
```

- [ ] **Step 4: `endpoints/api_admin.py`**

Line 122 currently:

```python
    base_url = request.app.state.users_settings.base_url
```

Replace with:

```python
    base_url = request.app.state.users.settings.base_url
```

- [ ] **Step 5: `endpoints/views.py` — remaining users-settings reads**

Lines 25, 58, 68 currently reference `request.app.state.users_settings`. Replace each with `request.app.state.users.settings`.

Before:

```python
    users_settings = request.app.state.users_settings
    ...
    cookie_name = request.app.state.users_settings.cookie_name
    ...
    if not request.app.state.users_settings.allow_signup:
```

After:

```python
    users_settings = request.app.state.users.settings
    ...
    cookie_name = request.app.state.users.settings.cookie_name
    ...
    if not request.app.state.users.settings.allow_signup:
```

- [ ] **Step 6: `roles_cache.py` — read/write via `users` slot**

Lines 41-47 currently:

```python
async def refresh_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Reload the roles list from the DB into ``app.state.users_roles_cache``."""
    async with app.state.db.session_factory() as db:
        result = await db.execute(select(Role).order_by(Role.name))
        cached = [RoleSummary(id=str(r.id), name=r.name) for r in result.scalars().all()]
    setattr(app.state, _ROLES_CACHE_KEY, cached)
    return cached
```

Replace with:

```python
async def refresh_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Reload the roles list from the DB into ``app.state.users.roles_cache``."""
    async with app.state.sm.db.session_factory() as db:
        result = await db.execute(select(Role).order_by(Role.name))
        cached = [RoleSummary(id=str(r.id), name=r.name) for r in result.scalars().all()]
    app.state.users.roles_cache = cached
    # Deprecated loose alias — removed Phase 4.
    setattr(app.state, _ROLES_CACHE_KEY, cached)
    return cached
```

Lines 50-62 (`get_roles_cache`) currently:

```python
async def get_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Return the cached roles list, populating it from the DB on first miss.
    ...
    """
    cached = getattr(app.state, _ROLES_CACHE_KEY, None)
    if cached:
        return cached
    return await refresh_roles_cache(app)
```

Replace with:

```python
async def get_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Return the cached roles list, populating it from the DB on first miss.

    The cache is pre-warmed in ``UsersModule.on_startup``. The lazy fallback
    covers scenarios where startup ran before the ``users_role`` table had any
    rows. Once populated, subsequent calls are O(1) attribute reads.
    """
    users = getattr(app.state, "users", None)
    cached = users.roles_cache if users is not None else []
    if cached:
        return cached
    return await refresh_roles_cache(app)
```

- [ ] **Step 7: Run the users suite**

```bash
uv run pytest modules/users/tests -x
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add modules/users/users/manager.py modules/users/users/deps.py modules/users/users/endpoints/api.py modules/users/users/endpoints/api_admin.py modules/users/users/endpoints/views.py modules/users/users/roles_cache.py
git commit -m "refactor(users): read module state via app.state.users"
```

---

### Task 9: Update users tests that write to `app.state` directly

Two test files poke `app.state` directly. Migrate them to the new shape — otherwise they paper over real regressions when loose keys are deleted in Phase 4.

**Files:**
- Modify: `modules/users/tests/test_api_auth.py`
- Modify: `modules/users/tests/conftest.py` (if it references deprecated keys)

- [ ] **Step 1: Update `test_api_auth.py`**

Line 141 currently:

```python
        settings = users_app.state.users_settings
```

Replace with:

```python
        settings = users_app.state.users.settings
```

Line 204 currently:

```python
        users_app.state.auth_throughput_limiter = ThroughputLimiter(
```

Replace with:

```python
        users_app.state.users.auth_throughput_limiter = ThroughputLimiter(
```

(Only the target changes — the arguments on the following lines are unchanged.)

- [ ] **Step 2: Audit `modules/users/tests/conftest.py`**

Open the file and scan for any `app.state.users_settings`, `app.state.mailer`, `app.state.rate_limiter`, `app.state.auth_throughput_limiter`, `app.state.users_roles_cache` references. For each, rewrite to the `app.state.users.<field>` form. If the fixture builds a `UsersServices` from scratch for a mock app, add:

```python
from users.services import UsersServices
app.state.users = UsersServices(settings=...)
```

immediately before any field assignment. Any existing loose writes can be deleted inside the same fixture.

- [ ] **Step 3: Run the full users suite**

```bash
uv run pytest modules/users/tests -x
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add modules/users/tests
git commit -m "test(users): migrate app.state reads/writes to app.state.users"
```

---

## Phase 4 — Cleanup

### Task 10: Delete deprecated loose keys from `app_builder.py` and users module

Now that every consumer reads through `app.state.sm.*` or `app.state.users.*`, remove the deprecated aliases.

**Files:**
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`
- Modify: `modules/users/users/module.py`
- Modify: `modules/users/users/roles_cache.py`

- [ ] **Step 1: `app_builder.py` — remove framework loose keys**

Delete lines 161-168 (the block assigning `app.state.modules` through `app.state.i18n_registry`). Keep `app.state.inertia_config` and `app.state.inertia_dependency` writes in `_inertia_setup.py` (they're framework internals read by `Services` + the loose `inertia_dependency` slot).

Before (lines 161-168):

```python
    app.state.modules = modules
    app.state.menu_registry = menu_registry
    app.state.perm_registry = perm_registry
    app.state.ff_registry = ff_registry
    app.state.event_bus = event_bus
    app.state.health_registry = health_registry
    app.state.settings = settings
    app.state.i18n_registry = i18n_registry
```

After: lines 161-168 are deleted. The `app.state.inertia_config = inertia_config` write in `_inertia_setup.py` stays (it's read by the `Services` constructor at the end of `create_app`).

Also delete line 211:

```python
    app.state.db = db_state
```

`db_state` is passed into the `Services(...)` constructor directly — no loose key needed.

- [ ] **Step 2: `module.py` (users) — remove deprecated aliases**

In `UsersModule.register_settings`, delete the deprecated-alias line added in Task 7 Step 2:

```python
        app.state.users_settings = services.settings  # deprecated loose alias, removed Phase 4
```

In `UsersModule.on_startup`, delete the deprecated-alias block added in Task 7 Step 2:

```python
        # Deprecated loose aliases — removed Phase 4.
        app.state.mailer = services.mailer
        app.state.rate_limiter = services.rate_limiter
        app.state.auth_throughput_limiter = services.auth_throughput_limiter
```

- [ ] **Step 3: `roles_cache.py` — remove deprecated alias**

Delete the deprecated alias added in Task 8 Step 6:

```python
    # Deprecated loose alias — removed Phase 4.
    setattr(app.state, _ROLES_CACHE_KEY, cached)
```

Also delete the now-unused `_ROLES_CACHE_KEY` constant near the top of the file (line 30) and the single remaining reference on what used to be the `getattr(app.state, _ROLES_CACHE_KEY, None)` line (already rewritten in Task 8 Step 6 — verify it's gone).

- [ ] **Step 4: Run the full test suite**

```bash
make test
```

Expected: all green. Any failure here means a consumer was missed in Phase 2 or 3 — find and migrate it, then rerun.

- [ ] **Step 5: Commit**

```bash
git add framework/hosting/simple_module_hosting/app_builder.py modules/users/users/module.py modules/users/users/roles_cache.py
git commit -m "refactor: delete deprecated loose app.state keys"
```

---

### Task 11: Delete duplicate locale fields, drift detection, and update SM012

**Files:**
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`
- Modify: `framework/hosting/simple_module_hosting/_phase_helpers.py`
- Modify: `host/routes_i18n.py`
- Modify: `host/tests/test_routes_i18n.py`

- [ ] **Step 1: Drop duplicate locale fields from `app_builder.py`**

Delete lines (post Task 10 renumbering) corresponding to the original:

```python
    app.state.settings_default_locale = settings.i18n_default_locale
    app.state.settings_supported_locales = settings.i18n_supported_locales
    app.state.settings_cookie_name = settings.i18n_cookie_name
```

- [ ] **Step 2: Drop the drift-detection block from `app_builder.py`**

Delete the block that checks `state_before`/`state_after` (originally lines 176-183):

```python
    state_before = set(app.state._state)
    for mod in modules:
        mod.register_settings(app)

    # SM012: warn if register_settings was overridden but added nothing
    if settings.is_development:
        state_after = set(app.state._state)
        check_settings_registration(modules, state_after - state_before)
```

Replace with:

```python
    for mod in modules:
        mod.register_settings(app)

    if settings.is_development:
        check_settings_registration(modules)
```

- [ ] **Step 3: Update `check_settings_registration` to the new convention**

In `framework/hosting/simple_module_hosting/_phase_helpers.py`, replace the `check_settings_registration` function (currently lines 132-156) with:

```python
def check_settings_registration(app: FastAPI, modules: list) -> None:
    """SM012: warn if a module overrides register_settings but added nothing to app.state.

    New convention (2026-04-17): modules store their state at
    ``app.state.<module_lower>`` as a module-owned dataclass.
    """
    for mod in modules:
        cls = type(mod)
        if "register_settings" not in cls.__dict__:
            continue
        mod_prefix = mod.meta.name.lower()
        if hasattr(app.state, mod_prefix):
            continue
        diag = Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM012",
            message="register_settings() was overridden but added nothing to app.state",
            module_name=mod.meta.name,
            suggestion=(
                f"Store your module state on app.state "
                f"(e.g., app.state.{mod_prefix} = {mod.meta.name}Services(...))"
            ),
        )
        logger.warning("%s", diag)
```

Then in `app_builder.py`, the single call site becomes:

```python
    if settings.is_development:
        check_settings_registration(app, modules)
```

- [ ] **Step 4: Update `host/routes_i18n.py` to drop the fallback branch**

Now that every test path goes through a real `create_app` (or builds `app.state.sm` explicitly), drop the fallback:

```python
    sm = getattr(request.app.state, "sm", None)
    if sm is not None:
        supported = sm.i18n_registry.available_locales()
        cookie_name: str = sm.settings.i18n_cookie_name
    else:
        # Fallback for tests that build a minimal app without Services.
        supported = request.app.state.settings_supported_locales
        cookie_name = request.app.state.settings_cookie_name
```

Replace with:

```python
    sm = request.app.state.sm
    supported = sm.i18n_registry.available_locales()
    cookie_name: str = sm.settings.i18n_cookie_name
```

- [ ] **Step 5: Rewrite `host/tests/test_routes_i18n.py` fixture**

Lines 11-16 currently:

```python
def _build_app(supported: list[str]) -> FastAPI:
    app = FastAPI()
    app.state.settings_supported_locales = supported
    app.state.settings_cookie_name = "locale"
    app.include_router(i18n_router)
    return app
```

Replace with:

```python
def _build_app(supported: list[str]) -> FastAPI:
    from types import SimpleNamespace

    from simple_module_core.i18n import I18nRegistry

    app = FastAPI()
    registry = I18nRegistry()
    for locale in supported:
        registry.register_namespace("ui", locale, {})
    settings = SimpleNamespace(i18n_cookie_name="locale")
    app.state.sm = SimpleNamespace(i18n_registry=registry, settings=settings)
    app.include_router(i18n_router)
    return app
```

The tests call `registry.available_locales()`, which returns the locales with loaded messages. Registering an empty dict for each is the minimum to pass validation.

- [ ] **Step 6: Run the host + hosting suites**

```bash
uv run pytest host/tests framework/hosting/tests -x
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add framework/hosting/simple_module_hosting/app_builder.py framework/hosting/simple_module_hosting/_phase_helpers.py host/routes_i18n.py host/tests/test_routes_i18n.py
git commit -m "refactor: drop duplicate locale fields, update SM012, simplify i18n routes"
```

---

### Task 12: Update `host/templates/index.html`

**Files:**
- Modify: `host/templates/index.html`

- [ ] **Step 1: Update template reads**

Lines 11 and 13 currently:

```html
    {% if request.app.state.inertia_config.environment == "development" %}
    <script type="module">
      import RefreshRuntime from "{{ request.app.state.inertia_config.dev_url }}/@react-refresh";
```

Replace with:

```html
    {% if request.app.state.sm.inertia_config.environment == "development" %}
    <script type="module">
      import RefreshRuntime from "{{ request.app.state.sm.inertia_config.dev_url }}/@react-refresh";
```

- [ ] **Step 2: Remove the now-unused loose `inertia_config` write**

In `framework/hosting/simple_module_hosting/_inertia_setup.py` line 67, the assignment `app.state.inertia_config = inertia_config` is still needed during boot because `Services(...)` reads it from `app.state.inertia_config` (set in Task 2 Step 3). Replace the `Services` construction in `app_builder.py` to take `inertia_config` directly.

Find the `Services(...)` construction block added in Task 2 Step 3; the line reads:

```python
        inertia_config=app.state.inertia_config,
```

Refactor the boot so `setup_inertia` returns the config rather than stashing it loose. In `_inertia_setup.py`, change the signature and return type:

```python
def setup_inertia(
    app: FastAPI,
    settings: Settings,
    modules: list,
    project_root: Path,
) -> InertiaConfig | None:
```

At the end of the function, replace:

```python
    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_config = inertia_config
    app.state.inertia_dependency = inertia_dep
```

with:

```python
    inertia_dep = inertia_dependency_factory(inertia_config)
    app.state.inertia_dependency = inertia_dep
    return inertia_config
```

And in the early `return` on line 51 (when no template directories exist), return `None`:

```python
    if not directories:
        logger.warning("No usable template directories — Inertia will fail to render views")
        return None
```

In `app_builder.py`, update the caller:

```python
    inertia_config = setup_inertia(app, settings, modules, _PROJECT_ROOT)
```

Then the `Services(...)` line becomes:

```python
        inertia_config=inertia_config,
```

(If `inertia_config` is `None`, the boot cannot proceed anyway — make this explicit. Add a guard before `Services(...)`:

```python
    if inertia_config is None:
        raise RuntimeError("Inertia not configured — no template directories available")
```

)

- [ ] **Step 3: Verify template updates via e2e tests**

```bash
uv run pytest framework/hosting/tests host/tests -x
```

Then run the dev server briefly to confirm the template still renders:

```bash
make dev
```

Browse `http://localhost:8000` — page should load without Jinja errors. Stop with `make kill`.

- [ ] **Step 4: Commit**

```bash
git add host/templates/index.html framework/hosting/simple_module_hosting/_inertia_setup.py framework/hosting/simple_module_hosting/app_builder.py
git commit -m "refactor(hosting): plumb inertia_config via return value instead of app.state"
```

---

### Task 13: Update scaffolding templates + docs

**Files:**
- Modify: `framework/hosting/simple_module_hosting/templates/module/__PACKAGE__/module.py.tpl`
- Create: `framework/hosting/simple_module_hosting/templates/module/__PACKAGE__/services.py.tpl`
- Modify: `scripts/new_module.py` (emit the new file)
- Modify: `scripts/_templates_tests.py` (if it references old state shape)
- Modify: `docs/framework-conventions.md`

- [ ] **Step 1: Inspect the current module template**

```bash
cat framework/hosting/simple_module_hosting/templates/module/__PACKAGE__/module.py.tpl
```

- [ ] **Step 2: Add a `services.py.tpl`**

Create `framework/hosting/simple_module_hosting/templates/module/__PACKAGE__/services.py.tpl` using the same placeholder tokens the existing `module.py.tpl` uses (inspected in Step 1). Based on the current scaffolding convention (`__PACKAGE__` for package path + lowercased name, `__CLASS__` for the PascalCase name):

```python
"""Module-scoped state container.

Stored as ``app.state.__PACKAGE__`` by
:meth:`__CLASS__Module.register_settings`.

Not frozen — ``on_startup`` may set fields that depend on the DB or
other framework services. Convention: set once during boot, treat as
read-only after.
"""

from __future__ import annotations

from dataclasses import dataclass

from __PACKAGE__.settings import __CLASS__Settings


@dataclass
class __CLASS__Services:
    """__CLASS__ module singletons."""

    settings: __CLASS__Settings
```

If Step 1's inspection shows different tokens (e.g. Jinja-style `{{ package }}`), adjust accordingly before saving — the scaffolding tests in `scripts/_templates_tests.py` lock the exact rendered output.

- [ ] **Step 3: Update the module template**

In the existing `module.py.tpl`, rewrite `register_settings` to use the new convention. Before (typical):

```python
    def register_settings(self, app: FastAPI) -> None:
        from __PACKAGE__.settings import __CLASS__Settings

        app.state.__PACKAGE___settings = __CLASS__Settings()
```

After:

```python
    def register_settings(self, app: FastAPI) -> None:
        from __PACKAGE__.services import __CLASS__Services
        from __PACKAGE__.settings import __CLASS__Settings

        app.state.__PACKAGE__ = __CLASS__Services(settings=__CLASS__Settings())
```

- [ ] **Step 4: Update `scripts/new_module.py`**

Find the list of template files it iterates over. Add `services.py.tpl`. If the scaffolder has a test that asserts the list of generated files, update it accordingly.

- [ ] **Step 5: Update `scripts/_templates_tests.py`**

Review `scripts/_templates_tests.py` for any references to the old state shape (`app.state.<module>_settings`). Update accordingly so generated-module tests run against the new convention.

- [ ] **Step 6: Update `docs/framework-conventions.md`**

Find the section "Module settings should:" (near the settings documentation). Replace the bullets:

Before:

```
- Use a per-module prefix: `SM_<MODULE>_*` (e.g. `SM_USERS_ALLOW_SIGNUP`).
- Be stored on `app.state.<module>_settings` during `register_settings(app)`.
- `SM012` diagnostic fires if `register_settings` is overridden but no `app.state.<module>_settings` is added.
```

After:

```
- Use a per-module prefix: `SM_<MODULE>_*` (e.g. `SM_USERS_ALLOW_SIGNUP`).
- Be stored inside a module-owned dataclass at `app.state.<module_lower>` during `register_settings(app)`.
- `SM012` diagnostic fires if `register_settings` is overridden but no `app.state.<module_lower>` entry is added.
```

Also replace the settings example on the same page (for the `AuthModule`). Before:

```python
class AuthModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.auth_settings = AuthSettings()
```

After:

```python
class AuthModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        app.state.auth = AuthServices(settings=AuthSettings())
```

Finally, add a short "Framework state" subsection (right before or after "Module settings") documenting `app.state.sm`:

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
```

- [ ] **Step 7: Run scaffolder tests**

```bash
uv run pytest framework/hosting/tests/test_scaffolding_module.py framework/hosting/tests/test_scaffolding_host.py -x
```

Expected: all green. If a scaffolding test compares rendered output against fixture strings, update the fixtures to match the new template.

- [ ] **Step 8: Smoke-test scaffolding by generating a module**

```bash
make new-module name=plan_scratch
make test  # runs the newly generated module tests
rm -rf modules/plan_scratch
```

Expected: `make test` passes, including the scaffolded module's tests.

- [ ] **Step 9: Commit**

```bash
git add framework/hosting/simple_module_hosting/templates modules/**/services.py scripts/new_module.py scripts/_templates_tests.py docs/framework-conventions.md
git commit -m "docs+scaffold: adopt app.state.sm + app.state.<module> convention"
```

---

### Task 14: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Full lint**

```bash
make lint
```

Expected: exit 0. Any ty (type checker) failure here means a type annotation wasn't updated — fix it inline.

- [ ] **Step 2: Full test suite**

```bash
make test
```

Expected: exit 0.

- [ ] **Step 3: Dev-server smoke test**

```bash
make dev
```

Browse:
- `http://localhost:8000/` — landing page renders.
- `http://localhost:8000/users/login` — login page renders (dev_accounts panel populated if bootstrap env vars set).
- `http://localhost:8000/products` — authenticated view renders.
- `http://localhost:8000/health` — returns `{"status": "healthy", ...}`.
- `http://localhost:8000/health/ready` — returns readiness JSON.

Stop with `make kill`.

- [ ] **Step 4: Grep audit — no lingering loose-key references**

```bash
grep -rn "app\.state\.menu_registry\|app\.state\.perm_registry\|app\.state\.ff_registry\|app\.state\.event_bus\|app\.state\.health_registry\|app\.state\.i18n_registry\|app\.state\.users_settings\|app\.state\.mailer\b\|app\.state\.rate_limiter\|app\.state\.auth_throughput_limiter\|app\.state\.users_roles_cache\|app\.state\.settings_default_locale\|app\.state\.settings_supported_locales\|app\.state\.settings_cookie_name" framework/ modules/ host/ scripts/ docs/
```

Expected: no hits (except in docs files that are listing historical context, which we'd already have edited in Task 13). Any remaining hit is a consumer that needs migration — find, fix, retest.

- [ ] **Step 5: Final commit if the verification needed any fixes**

```bash
git add -A
git commit -m "chore: post-verification fixes for app.state migration"
```

(Skip this step if Steps 1–4 passed cleanly.)

---

## Rollback

Each task is a single commit and independently revertable. If a later phase uncovers a regression tied to an earlier task, revert that task's commit and any dependents; `main` is green at each commit boundary.
