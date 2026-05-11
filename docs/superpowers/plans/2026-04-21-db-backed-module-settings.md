# DB-backed Module Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `SM_<MODULE>_*` env-var sprawl with DB-backed overrides behind every module's pydantic `BaseSettings`, plus a typed admin UI at `/settings/modules` that supports hot-reload and per-field "Requires restart" semantics.

**Architecture:** Pydantic `BaseSettings` classes become pure schemas (no env reading). A new `ModuleSettingsRegistry` tracks `{package: BaseSettings_cls}`. A framework-level hydration step, run at the start of the FastAPI lifespan before any module `on_startup`, resolves each module's effective settings from `DB value > pydantic default` and reassigns `app.state.<package>.settings`. UI saves hit a new API that validates (by constructing the `BaseSettings`), writes deltas to the existing `Setting` table under `scope="system"`, reassigns `app.state`, and publishes a `SettingsReloaded` event. Host-level env is reduced to a small bootstrap group; power users can still set rarely-touched host knobs via env too.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, pydantic-settings, SQLModel, SQLAlchemy async, Inertia.js, React 18, Tailwind 4, Vite.

**Spec:** [docs/superpowers/specs/2026-04-21-db-backed-module-settings-design.md](../specs/2026-04-21-db-backed-module-settings-design.md)

---

## Phase 0: Safety net

### Task 0.1: Verify clean baseline

**Files:** none

- [ ] **Step 1: Run the full test suite to confirm the starting point is green**

Run: `make test`
Expected: PASS (both `test-py` and `test-js`).

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: PASS.

- [ ] **Step 3: Run doctor**

Run: `make doctor`
Expected: PASS.

If any of these fail, stop and fix the existing breakage before proceeding — subsequent tasks assume a green baseline.

---

## Phase 1: Framework plumbing — registry, hydrator, store

All work lives in `modules/settings/settings/` so the Settings module owns the DB-backed config mechanism.

### Task 1.1: Add `ModuleSettingsRegistry`

**Files:**
- Create: `modules/settings/settings/module_registry.py`
- Test: `modules/settings/tests/test_module_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_module_registry.py
"""Tests for ModuleSettingsRegistry — tracks {package: BaseSettings_cls}."""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from settings.module_registry import ModuleSettingsRegistry


class _Foo(BaseSettings):
    x: int = 7


class _Bar(BaseSettings):
    y: str = "z"


def test_register_and_get() -> None:
    r = ModuleSettingsRegistry()
    r.register("foo", _Foo)
    assert r.get("foo") is _Foo


def test_register_duplicate_raises() -> None:
    r = ModuleSettingsRegistry()
    r.register("foo", _Foo)
    with pytest.raises(ValueError, match="already registered"):
        r.register("foo", _Foo)


def test_all_packages_sorted() -> None:
    r = ModuleSettingsRegistry()
    r.register("bar", _Bar)
    r.register("foo", _Foo)
    assert r.all_packages() == ["bar", "foo"]


def test_get_missing_returns_none() -> None:
    assert ModuleSettingsRegistry().get("nope") is None
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest modules/settings/tests/test_module_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings.module_registry'`.

- [ ] **Step 3: Implement the registry**

```python
# modules/settings/settings/module_registry.py
"""Registry of per-module pydantic BaseSettings classes.

Populated during each module's ``register_settings`` via
``register_module_settings``. The hosting lifespan reads this at startup
to hydrate every module's effective settings from the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_settings import BaseSettings


@dataclass(slots=True)
class ModuleSettingsRegistry:
    """In-memory map of ``package`` → ``BaseSettings`` subclass."""

    _classes: dict[str, type[BaseSettings]] = field(default_factory=dict)

    def register(self, package: str, cls: type[BaseSettings]) -> None:
        if package in self._classes:
            raise ValueError(f"{package!r} already registered")
        self._classes[package] = cls

    def get(self, package: str) -> type[BaseSettings] | None:
        return self._classes.get(package)

    def all_packages(self) -> list[str]:
        return sorted(self._classes)

    def items(self) -> list[tuple[str, type[BaseSettings]]]:
        return sorted(self._classes.items())
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `uv run pytest modules/settings/tests/test_module_registry.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/settings/settings/module_registry.py modules/settings/tests/test_module_registry.py
git commit -m "feat(settings): add ModuleSettingsRegistry for per-module BaseSettings classes"
```

---

### Task 1.2: Add `SettingsStore` — namespaced k/v over `Setting` table

**Files:**
- Create: `modules/settings/settings/store.py`
- Test: `modules/settings/tests/test_store.py`

The store uses the existing `Setting` table with `scope="system"`, `scope_id="system"`, and `key="<package>.<field>"`.

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_store.py
"""Round-trip tests for SettingsStore — namespaced k/v over the Setting table."""

from __future__ import annotations

import pytest

from settings.service import SettingService
from settings.store import SettingsStore


@pytest.mark.asyncio
async def test_set_and_get_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("users", "smtp_port", "587", "int")
    await store.set_override("background_tasks", "retention_days", "30", "int")

    users = await store.get_overrides("users")
    assert users == {
        "allow_signup": ("true", "bool"),
        "smtp_port": ("587", "int"),
    }
    bg = await store.get_overrides("background_tasks")
    assert bg == {"retention_days": ("30", "int")}


@pytest.mark.asyncio
async def test_set_override_updates_existing(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("users", "allow_signup", "false", "bool")

    assert await store.get_overrides("users") == {"allow_signup": ("false", "bool")}


@pytest.mark.asyncio
async def test_clear_override(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.clear_override("users", "allow_signup")

    assert await store.get_overrides("users") == {}


@pytest.mark.asyncio
async def test_clear_override_missing_is_noop(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.clear_override("users", "does_not_exist")  # must not raise


@pytest.mark.asyncio
async def test_list_packages_with_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")
    await store.set_override("background_tasks", "retention_days", "7", "int")

    assert await store.list_packages_with_overrides() == ["background_tasks", "users"]
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings.store'`.

- [ ] **Step 3: Implement the store**

```python
# modules/settings/settings/store.py
"""DB-backed key/value store for module settings (SYSTEM scope).

Wraps the existing SettingService. Keys are namespaced ``<package>.<field>``
to avoid collision with free-form user-defined setting keys.
"""

from __future__ import annotations

from settings.constants import SCOPE_SYSTEM, SYSTEM_SCOPE_ID
from settings.contracts.schemas import SettingScope, SettingUpsert, SettingValueType
from settings.service import SettingService


def _key(package: str, field: str) -> str:
    return f"{package}.{field}"


class SettingsStore:
    """SYSTEM-scoped key/value store keyed by ``(package, field)``."""

    def __init__(self, service: SettingService) -> None:
        self._service = service

    async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]:
        """Return ``{field_name: (raw_value, value_type)}`` for a package."""
        prefix = f"{package}."
        items = await self._service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        out: dict[str, tuple[str, str]] = {}
        for item in items:
            if not item.key.startswith(prefix):
                continue
            field_name = item.key[len(prefix):]
            # Skip nested keys — namespaces are flat for module settings.
            if "." in field_name:
                continue
            out[field_name] = (item.value, item.value_type)
        return out

    async def set_override(
        self, package: str, field: str, value: str, value_type: str
    ) -> None:
        await self._service.upsert_scoped(
            SettingScope.SYSTEM,
            SYSTEM_SCOPE_ID,
            _key(package, field),
            SettingUpsert(value=value, value_type=SettingValueType(value_type)),
        )

    async def clear_override(self, package: str, field: str) -> None:
        await self._service.delete_scoped(
            SettingScope.SYSTEM, SYSTEM_SCOPE_ID, _key(package, field)
        )

    async def list_packages_with_overrides(self) -> list[str]:
        items = await self._service.list_by_scope(SettingScope.SYSTEM, SYSTEM_SCOPE_ID)
        pkgs: set[str] = set()
        for item in items:
            if "." not in item.key:
                continue
            pkg, rest = item.key.split(".", 1)
            if "." in rest:
                continue  # ignore deeper nests
            pkgs.add(pkg)
        return sorted(pkgs)
```

If `SettingValueType` does not already exist as an enum that accepts the string, verify `modules/settings/settings/contracts/schemas.py` exposes it. If not, add it in Task 1.3 before proceeding.

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_store.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/settings/settings/store.py modules/settings/tests/test_store.py
git commit -m "feat(settings): add SettingsStore for module-namespaced overrides"
```

---

### Task 1.3: Extend `SettingValueType` / `SettingScope` enums if missing

**Files:**
- Modify: `modules/settings/settings/contracts/schemas.py` (if needed)

- [ ] **Step 1: Verify `SettingValueType` and `SettingScope` exist**

Run: `uv run python -c "from settings.contracts.schemas import SettingValueType, SettingScope; print(list(SettingValueType))"`
Expected: Prints the enum members. If ImportError, add the enum.

- [ ] **Step 2: If needed, add the missing enum members to match `constants.VALUE_TYPE_*`**

Ensure `SettingValueType` has exactly: `STRING="string"`, `BOOL="bool"`, `INT="int"`, `FLOAT="float"`, `JSON="json"`. Add any missing.

- [ ] **Step 3: Rerun Task 1.2 tests to confirm they still pass**

Run: `uv run pytest modules/settings/tests/test_store.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit if any changes were made**

```bash
git add modules/settings/settings/contracts/schemas.py
git commit -m "chore(settings): ensure SettingValueType covers all stored value types" || true
```

---

### Task 1.4: Hydrator — parse DB overrides into a `BaseSettings` instance

**Files:**
- Create: `modules/settings/settings/hydrate.py`
- Test: `modules/settings/tests/test_hydrate.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_hydrate.py
"""Tests for hydrate_settings — resolve DB overrides into a BaseSettings instance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings

from settings.hydrate import hydrate_settings, value_type_for_field
from settings.service import SettingService
from settings.store import SettingsStore


class _Cfg(BaseSettings):
    allow: bool = False
    port: int = 25
    host: str = "localhost"
    tags: list[str] = ["a"]
    rate: float = 1.5


@pytest.mark.asyncio
async def test_hydrate_returns_defaults_when_no_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg == _Cfg()


@pytest.mark.asyncio
async def test_hydrate_applies_scalar_overrides(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "allow", "true", "bool")
    await store.set_override("demo", "port", "587", "int")
    await store.set_override("demo", "host", "mail.example.com", "string")
    await store.set_override("demo", "rate", "2.5", "float")

    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.allow is True
    assert cfg.port == 587
    assert cfg.host == "mail.example.com"
    assert cfg.rate == 2.5


@pytest.mark.asyncio
async def test_hydrate_applies_json_list_override(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "tags", '["x","y","z"]', "json")
    cfg = await hydrate_settings(_Cfg, store, package="demo")
    assert cfg.tags == ["x", "y", "z"]


@pytest.mark.asyncio
async def test_hydrate_raises_on_pydantic_validation_error(db_session) -> None:
    store = SettingsStore(SettingService(db_session))
    await store.set_override("demo", "port", "not-an-int", "int")
    with pytest.raises(ValidationError):
        await hydrate_settings(_Cfg, store, package="demo")


def test_value_type_for_bool_int_float_str_list() -> None:
    assert value_type_for_field(_Cfg, "allow") == "bool"
    assert value_type_for_field(_Cfg, "port") == "int"
    assert value_type_for_field(_Cfg, "rate") == "float"
    assert value_type_for_field(_Cfg, "host") == "string"
    assert value_type_for_field(_Cfg, "tags") == "json"
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_hydrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'settings.hydrate'`.

- [ ] **Step 3: Implement the hydrator**

```python
# modules/settings/settings/hydrate.py
"""Resolve a module's BaseSettings from DB overrides + pydantic defaults.

A field's declared Python type maps to one of the five ``value_type`` labels
understood by SettingsStore (``string | bool | int | float | json``). The
hydrator reads overrides, parses each according to its stored ``value_type``,
and constructs the BaseSettings — pydantic enforces field validators and any
``@model_validator`` hooks.
"""

from __future__ import annotations

import json
from typing import TypeVar, get_args, get_origin

from pydantic_settings import BaseSettings

from settings.store import SettingsStore

T = TypeVar("T", bound=BaseSettings)


def value_type_for_field(cls: type[BaseSettings], field_name: str) -> str:
    """Return the ``value_type`` label for a field based on its annotation.

    - ``bool`` → ``"bool"``
    - ``int`` → ``"int"``
    - ``float`` → ``"float"``
    - ``str`` and enums → ``"string"``
    - ``list``, ``dict``, and other container types → ``"json"``
    """
    info = cls.model_fields[field_name]
    ann = info.annotation
    origin = get_origin(ann)
    if origin is not None:
        # list[...], dict[...], list[...] | None, etc. → json
        return "json"
    if ann is bool:
        return "bool"
    if ann is int:
        return "int"
    if ann is float:
        return "float"
    # str, Literal[...], enum classes, and anything else scalar → string
    return "string"


def _parse(raw: str, value_type: str):  # noqa: ANN202 (pydantic accepts Any)
    if value_type == "bool":
        return raw.lower() in ("1", "true", "yes", "on")
    if value_type == "int":
        return int(raw)
    if value_type == "float":
        return float(raw)
    if value_type == "json":
        return json.loads(raw)
    return raw


async def hydrate_settings(cls: type[T], store: SettingsStore, package: str) -> T:
    """Construct ``cls`` with DB overrides merged over pydantic defaults."""
    raw_overrides = await store.get_overrides(package)
    parsed: dict[str, object] = {}
    for field_name, (raw, vtype) in raw_overrides.items():
        if field_name not in cls.model_fields:
            continue  # stale field in DB — silently skip; prune-orphans handles it
        parsed[field_name] = _parse(raw, vtype)
    return cls(**parsed)  # pydantic runs validators here
```

Note the `_ = get_args(ann)` is intentionally unused — `get_origin` alone is enough for the current type set. If you're linting unused imports, remove `get_args` from the import.

- [ ] **Step 4: Remove unused import**

```python
from typing import TypeVar, get_origin
```

- [ ] **Step 5: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_hydrate.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add modules/settings/settings/hydrate.py modules/settings/tests/test_hydrate.py
git commit -m "feat(settings): add hydrate_settings and value_type inference"
```

---

### Task 1.5: `register_module_settings` helper + update `SettingsServices`

Modules currently set `app.state.<package>` in their own `register_settings` hook. This task introduces a helper that (a) constructs defaults, (b) registers the class in the registry, (c) sets `app.state.<package>.settings` so hooks see defaults before the hosting lifespan hydrates them.

**Files:**
- Modify: `modules/settings/settings/services.py`
- Create: `modules/settings/settings/registration.py`
- Test: `modules/settings/tests/test_registration.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_registration.py
"""Tests for register_module_settings — helper modules call during boot."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic_settings import BaseSettings

from settings.constants import MODULE_PACKAGE
from settings.module_registry import ModuleSettingsRegistry
from settings.registration import register_module_settings
from settings.services import SettingsServices
from settings.settings import SettingsSettings


class _FakeModuleServices:
    def __init__(self, settings):
        self.settings = settings


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.state.settings = SettingsServices(
        settings=SettingsSettings(),
        registry=__import__("settings.contracts.registry", fromlist=["SettingsRegistry"]).SettingsRegistry(),
        module_registry=ModuleSettingsRegistry(),
    )
    return app


class _UsersCfg(BaseSettings):
    allow: bool = False
    port: int = 25


def test_register_installs_defaults_on_app_state(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    assert isinstance(app.state.users, _FakeModuleServices)
    assert app.state.users.settings == _UsersCfg()


def test_register_adds_to_module_registry(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    assert app.state.settings.module_registry.get("users") is _UsersCfg


def test_register_duplicate_raises(app):
    register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
    with pytest.raises(ValueError, match="already registered"):
        register_module_settings(app, "users", _UsersCfg, _FakeModuleServices)
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_registration.py -v`
Expected: FAIL — imports or attribute errors.

- [ ] **Step 3: Add `module_registry` to `SettingsServices`**

Modify `modules/settings/settings/services.py`:

```python
"""Module-scoped state container.

Stored as ``app.state.settings`` by
:meth:`SettingsModule.register_settings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from settings.contracts.registry import SettingsRegistry
from settings.module_registry import ModuleSettingsRegistry
from settings.settings import SettingsSettings


@dataclass
class SettingsServices:
    """Settings module singletons."""

    settings: SettingsSettings
    registry: SettingsRegistry = field(default_factory=SettingsRegistry)
    module_registry: ModuleSettingsRegistry = field(default_factory=ModuleSettingsRegistry)
```

- [ ] **Step 4: Implement `register_module_settings`**

```python
# modules/settings/settings/registration.py
"""Helper modules call from ``register_settings`` to install their BaseSettings.

Two things happen:
1. A fresh ``BaseSettings`` (pydantic defaults only) is constructed.
2. The class is recorded in ``app.state.settings.module_registry`` so the
   hosting lifespan can hydrate it from the DB before module ``on_startup``
   hooks run.

The module's services dataclass is built from the default settings object and
attached at ``app.state.<package>``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from settings.constants import MODULE_PACKAGE


def register_module_settings(
    app: FastAPI,
    package: str,
    settings_cls: type[BaseSettings],
    services_factory: Callable[[BaseSettings], Any],
) -> None:
    """Register a module's BaseSettings class and mount its services on app.state.

    Args:
        app: The FastAPI app being built.
        package: The module's top-level package name (e.g. ``"users"``).
        settings_cls: The module's ``BaseSettings`` subclass.
        services_factory: Callable ``(settings) -> services_dataclass`` used to
            build the object stored at ``app.state.<package>``. Typically the
            module's own ``Services`` dataclass constructor.
    """
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    registry.register(package, settings_cls)
    defaults = settings_cls()
    setattr(app.state, package, services_factory(defaults))
```

- [ ] **Step 5: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_registration.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add modules/settings/settings/services.py modules/settings/settings/registration.py modules/settings/tests/test_registration.py
git commit -m "feat(settings): add register_module_settings helper + ModuleSettingsRegistry on SettingsServices"
```

---

### Task 1.6: `SettingsReloaded` event

**Files:**
- Create: `modules/settings/settings/contracts/events.py`
- Test: `modules/settings/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_events.py
from __future__ import annotations

import pytest
from simple_module_core.events import EventBus

from settings.contracts.events import SettingsReloaded


@pytest.mark.asyncio
async def test_publish_and_subscribe() -> None:
    bus = EventBus()
    received: list[SettingsReloaded] = []

    async def handler(evt: SettingsReloaded) -> None:
        received.append(evt)

    bus.subscribe(SettingsReloaded, handler)
    await bus.publish(SettingsReloaded(package="users", changed=("allow_signup",)))
    assert received == [SettingsReloaded(package="users", changed=("allow_signup",))]
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_events.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement the event**

```python
# modules/settings/settings/contracts/events.py
"""Domain events published by the Settings module."""

from __future__ import annotations

from dataclasses import dataclass

from simple_module_core.events import Event


@dataclass(frozen=True)
class SettingsReloaded(Event):
    """Fired after a module's BaseSettings has been reloaded from the DB.

    Subscribers that cached stateful handles built from settings (SMTP client,
    Celery app config, middleware) can rebuild when ``package`` matches their
    own.
    """

    package: str
    changed: tuple[str, ...]
```

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_events.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/settings/settings/contracts/events.py modules/settings/tests/test_events.py
git commit -m "feat(settings): add SettingsReloaded event"
```

---

### Task 1.7: Hot-reload on save

**Files:**
- Create: `modules/settings/settings/reload.py`
- Test: `modules/settings/tests/test_reload.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_reload.py
from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from simple_module_core.events import EventBus

from settings.contracts.events import SettingsReloaded
from settings.module_registry import ModuleSettingsRegistry
from settings.registration import register_module_settings
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.services import SettingsServices
from settings.settings import SettingsSettings
from settings.store import SettingsStore


class _UsersCfg(BaseSettings):
    allow_signup: bool = False
    smtp_port: int = 25


@dataclass
class _UsersServices:
    settings: _UsersCfg


@pytest.fixture
def app_and_bus(db_session) -> tuple[FastAPI, EventBus]:
    bus = EventBus()
    app = FastAPI()
    app.state.settings = SettingsServices(settings=SettingsSettings())
    register_module_settings(app, "users", _UsersCfg, lambda s: _UsersServices(settings=s))
    return app, bus


@pytest.mark.asyncio
async def test_apply_changes_updates_app_state_and_fires_event(app_and_bus, db_session):
    app, bus = app_and_bus
    received: list[SettingsReloaded] = []

    async def handler(evt: SettingsReloaded) -> None:
        received.append(evt)

    bus.subscribe(SettingsReloaded, handler)

    store = SettingsStore(SettingService(db_session))
    new_settings = await apply_changes_and_reload(
        app, bus, store, package="users",
        changes={"allow_signup": True, "smtp_port": 587},
    )

    assert new_settings.allow_signup is True
    assert new_settings.smtp_port == 587
    assert app.state.users.settings is new_settings
    assert received == [SettingsReloaded(package="users", changed=("allow_signup", "smtp_port"))]

    persisted = await store.get_overrides("users")
    assert persisted == {"allow_signup": ("True", "bool"), "smtp_port": ("587", "int")}


@pytest.mark.asyncio
async def test_apply_changes_validation_error_rolls_back(app_and_bus, db_session):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))

    original = app.state.users.settings

    with pytest.raises(ValidationError):
        await apply_changes_and_reload(
            app, bus, store, package="users",
            changes={"smtp_port": "not-an-int"},  # fails pydantic int coercion
        )

    assert app.state.users.settings is original
    assert await store.get_overrides("users") == {}


@pytest.mark.asyncio
async def test_apply_changes_unknown_package_raises(app_and_bus, db_session):
    app, bus = app_and_bus
    store = SettingsStore(SettingService(db_session))

    with pytest.raises(KeyError):
        await apply_changes_and_reload(
            app, bus, store, package="unknown", changes={"x": 1},
        )
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_reload.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `apply_changes_and_reload`**

```python
# modules/settings/settings/reload.py
"""Apply a set of field changes to a module's settings and reload them.

Steps:
1. Look up the module's BaseSettings class from the registry.
2. Merge changes over current DB overrides + defaults to form the candidate.
3. Construct ``cls(**candidate)`` — pydantic validates.
4. On success, write each change to the store, reassign ``app.state.<package>.settings``,
   and publish ``SettingsReloaded``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings
from simple_module_core.events import EventBus

from settings.constants import MODULE_PACKAGE
from settings.contracts.events import SettingsReloaded
from settings.hydrate import hydrate_settings, value_type_for_field
from settings.store import SettingsStore


def _encode(value: Any, value_type: str) -> str:
    if value_type == "json":
        return json.dumps(value)
    return str(value)


async def apply_changes_and_reload(
    app: FastAPI,
    bus: EventBus,
    store: SettingsStore,
    *,
    package: str,
    changes: dict[str, Any],
) -> BaseSettings:
    """Validate, persist, hot-swap, and publish ``SettingsReloaded``."""
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    cls = registry.get(package)
    if cls is None:
        raise KeyError(f"Unknown settings package: {package!r}")

    # Unknown fields are rejected loudly.
    unknown = set(changes) - set(cls.model_fields)
    if unknown:
        raise KeyError(f"Unknown field(s) for {package!r}: {sorted(unknown)}")

    # Merge over current hydrated state for pydantic validation.
    current = await hydrate_settings(cls, store, package)
    merged = current.model_dump()
    merged.update(changes)
    validated = cls(**merged)  # raises ValidationError on bad input

    # Persist only the requested fields — everything else stays in DB as-is.
    for field_name, raw_value in changes.items():
        vtype = value_type_for_field(cls, field_name)
        encoded = _encode(raw_value, vtype)
        await store.set_override(package, field_name, encoded, vtype)

    # Rebuild services object to keep the dataclass shape consistent, replacing
    # only the .settings attribute.
    services = getattr(app.state, package)
    services.settings = validated

    await bus.publish(SettingsReloaded(package=package, changed=tuple(sorted(changes))))
    return validated
```

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_reload.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add modules/settings/settings/reload.py modules/settings/tests/test_reload.py
git commit -m "feat(settings): add apply_changes_and_reload with validation + SettingsReloaded event"
```

---

## Phase 2: Hosting — bootstrap split + hydration in lifespan

### Task 2.1: Split `Settings` into `BootstrapSettings` + `HostSettings`

**Files:**
- Create: `framework/hosting/simple_module_hosting/bootstrap_settings.py`
- Create: `framework/hosting/simple_module_hosting/host_settings.py`
- Modify: `framework/hosting/simple_module_hosting/settings.py`
- Create: `tests/test_bootstrap_settings.py`

`BootstrapSettings` — env-driven, read before DB. Contains: `database_url`, `db_pool_*`, `environment`, `secret_key`, `vite_dev_url`, `debug`, `log_level`, `log_format`, `modules_enabled`.

`HostSettings` — defaults-only (DB-backed like modules). Contains: `multi_tenant`, `tenant_header`, `i18n_default_locale`, `i18n_supported_locales`, `i18n_cookie_name`.

The public `Settings` name is kept as a facade (combines both) so existing import sites keep working for the duration of Phase 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bootstrap_settings.py
from __future__ import annotations

import pytest

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


def test_bootstrap_reads_from_env(monkeypatch):
    monkeypatch.setenv("SM_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SM_SECRET_KEY", "x" * 48)
    monkeypatch.setenv("SM_ENVIRONMENT", "development")
    bs = BootstrapSettings()
    assert bs.database_url == "sqlite+aiosqlite:///:memory:"
    assert bs.secret_key == "x" * 48
    assert bs.environment == "development"


def test_bootstrap_placeholder_secret_blocks_production(monkeypatch):
    monkeypatch.setenv("SM_ENVIRONMENT", "production")
    monkeypatch.setenv("SM_SECRET_KEY", "change-me-in-production")
    with pytest.raises(ValueError, match="SM_SECRET_KEY"):
        BootstrapSettings()


def test_host_settings_ignores_env(monkeypatch):
    # HostSettings must NOT read env — env-sprawl is what we're removing.
    monkeypatch.setenv("SM_MULTI_TENANT", "true")
    hs = HostSettings()
    assert hs.multi_tenant is False  # default wins; env ignored


def test_host_settings_default_locale_must_be_supported():
    with pytest.raises(ValueError):
        HostSettings(i18n_default_locale="de", i18n_supported_locales=["en"])
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_bootstrap_settings.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `BootstrapSettings`**

```python
# framework/hosting/simple_module_hosting/bootstrap_settings.py
"""Env-only settings read before the database is available.

Everything here is needed either to connect to the DB, sign session cookies,
or configure the Python process (logging, Vite asset URLs, module allowlist).
These values stay in ``.env`` — all other settings live in the DB.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.environments import NON_PROD_ENVIRONMENTS

_PLACEHOLDER_SECRET_KEY = "change-me-in-production"


class BootstrapSettings(BaseSettings):
    """Pre-DB bootstrap environment knobs."""

    model_config = SettingsConfigDict(env_prefix="SM_", env_file=".env", extra="ignore")

    # Database — the only required env value in a typical deployment.
    database_url: str = "sqlite+aiosqlite:///./app.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_pool_recycle: int = 1800

    # Process identity
    environment: str = "development"
    secret_key: str = _PLACEHOLDER_SECRET_KEY
    vite_dev_url: str = "http://localhost:5050"
    debug: bool = False

    # Logging (configured before the DB is touched)
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Module allowlist — resolved before any DB access.
    modules_enabled: list[str] | None = None

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @model_validator(mode="after")
    def _forbid_placeholder_secret_in_production(self) -> "BootstrapSettings":
        if (
            self.environment not in NON_PROD_ENVIRONMENTS
            and self.secret_key == _PLACEHOLDER_SECRET_KEY
        ):
            raise ValueError(
                f"SM_SECRET_KEY must be set to a non-default value when "
                f"SM_ENVIRONMENT={self.environment!r}. Generate one with "
                "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
            )
        return self
```

- [ ] **Step 4: Implement `HostSettings`**

```python
# framework/hosting/simple_module_hosting/host_settings.py
"""Host-level settings stored in the DB (not env).

Registered under ``package="host"`` so the UI shows them alongside module
settings. The hosting layer still reads these directly from
``app.state.host.settings``.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HostSettings(BaseSettings):
    """DB-backed host configuration — defaults live here, overrides in DB."""

    # No env_prefix and no env_file: this class must never read environment.
    model_config = SettingsConfigDict(extra="ignore")

    # Multi-tenancy
    multi_tenant: bool = False
    tenant_header: str = ""

    # Internationalization
    i18n_default_locale: str = "en"
    i18n_supported_locales: list[str] = ["en"]
    i18n_cookie_name: str = "locale"

    @model_validator(mode="after")
    def _check_default_locale_supported(self) -> "HostSettings":
        if self.i18n_default_locale not in self.i18n_supported_locales:
            raise ValueError(
                f"i18n_default_locale '{self.i18n_default_locale}' is not in "
                f"i18n_supported_locales {self.i18n_supported_locales}"
            )
        return self
```

- [ ] **Step 5: Update `settings.py` to re-export for backwards-compat during migration**

```python
# framework/hosting/simple_module_hosting/settings.py
"""Back-compat shim — prefer BootstrapSettings + HostSettings directly.

During migration, existing code that imports ``Settings`` keeps working by
combining both classes. Once all call sites have migrated, this shim is
removed.
"""

from __future__ import annotations

from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings


class Settings(BootstrapSettings):
    """Combined bootstrap + host settings for legacy import sites.

    Host-level fields still come from class defaults; the env-driven fields
    come from BootstrapSettings. New code should import BootstrapSettings and
    HostSettings separately and read host fields from
    ``app.state.host.settings``.
    """

    # Carry the HostSettings fields as defaults for legacy consumers.
    multi_tenant: bool = HostSettings.model_fields["multi_tenant"].default
    tenant_header: str = HostSettings.model_fields["tenant_header"].default
    i18n_default_locale: str = HostSettings.model_fields["i18n_default_locale"].default
    i18n_supported_locales: list[str] = HostSettings.model_fields["i18n_supported_locales"].default
    i18n_cookie_name: str = HostSettings.model_fields["i18n_cookie_name"].default
```

- [ ] **Step 6: Run and confirm pass**

Run: `uv run pytest tests/test_bootstrap_settings.py -v`
Expected: 4 passed.

- [ ] **Step 7: Run full test suite — most should still pass**

Run: `uv run pytest -x`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add framework/hosting/simple_module_hosting/bootstrap_settings.py framework/hosting/simple_module_hosting/host_settings.py framework/hosting/simple_module_hosting/settings.py tests/test_bootstrap_settings.py
git commit -m "feat(hosting): split Settings into BootstrapSettings (env) + HostSettings (DB)"
```

---

### Task 2.2: Register `HostSettings` as `package="host"`

**Files:**
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`
- Test: added to `tests/test_bootstrap_settings.py`

This hooks `HostSettings` into the existing `ModuleSettingsRegistry` so the admin UI lists it alongside modules.

- [ ] **Step 1: Add the failing test to `tests/test_bootstrap_settings.py`**

```python
# append to tests/test_bootstrap_settings.py
@pytest.mark.asyncio
async def test_host_settings_registered_as_host_package(app):
    registry = app.state.settings.module_registry
    assert registry.get("host").__name__ == "HostSettings"
    assert isinstance(app.state.host.settings, __import__(
        "simple_module_hosting.host_settings", fromlist=["HostSettings"]
    ).HostSettings)
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_bootstrap_settings.py::test_host_settings_registered_as_host_package -v`
Expected: FAIL — no "host" entry.

- [ ] **Step 3: Register host in `create_app`**

Modify `framework/hosting/simple_module_hosting/app_builder.py` after Phase 4 (module settings registration, ~line 172):

```python
    # ── Phase 4: Module settings ───────────────────────────
    for mod in modules:
        mod.register_settings(app)

    # Register host-level settings under package="host" (DB-backed). The
    # Settings module must already have run register_settings (topo order
    # should put it early; its meta.depends_on = [] so it's scheduled first
    # among leaves).
    from dataclasses import dataclass
    from simple_module_hosting.host_settings import HostSettings
    from settings.registration import register_module_settings

    @dataclass
    class _HostServices:
        settings: HostSettings

    register_module_settings(app, "host", HostSettings, lambda s: _HostServices(settings=s))
```

Note: we create the dataclass inline to avoid yet another tiny module. If lint flags it, extract to `framework/hosting/simple_module_hosting/_host_services.py`.

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest tests/test_bootstrap_settings.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/app_builder.py tests/test_bootstrap_settings.py
git commit -m "feat(hosting): register HostSettings as package='host' in module registry"
```

---

### Task 2.3: Hydration step at start of lifespan

**Files:**
- Modify: `framework/hosting/simple_module_hosting/app_builder.py`
- Create: `framework/hosting/simple_module_hosting/_hydrate_step.py`
- Test: `tests/test_hydration_lifespan.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hydration_lifespan.py
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_lifespan_hydrates_host_settings_from_db(app, db_session):
    """After lifespan starts, host settings reflect DB overrides, not defaults."""
    from settings.service import SettingService
    from settings.store import SettingsStore

    # Seed an override before the lifespan's hydrate step would run.
    # (In this fixture, lifespan has already started — so we simulate by
    # writing an override and asking the hydrator to re-run.)
    store = SettingsStore(SettingService(db_session))
    await store.set_override("host", "multi_tenant", "true", "bool")

    from simple_module_hosting._hydrate_step import hydrate_all
    await hydrate_all(app, store)

    assert app.state.host.settings.multi_tenant is True
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest tests/test_hydration_lifespan.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `hydrate_all`**

```python
# framework/hosting/simple_module_hosting/_hydrate_step.py
"""Framework-level hydration step run at start of the FastAPI lifespan.

Walks every registered module (including ``host``), hydrates its BaseSettings
from the DB, and reassigns ``app.state.<package>.settings``. Runs before any
module ``on_startup`` hook so startup code sees DB-backed values.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.hydrate import hydrate_settings
from settings.store import SettingsStore

logger = logging.getLogger(__name__)


async def hydrate_all(app: FastAPI, store: SettingsStore) -> None:
    """Resolve every registered module's settings from the DB."""
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    for package, cls in registry.items():
        try:
            hydrated = await hydrate_settings(cls, store, package)
        except Exception:
            # One bad override shouldn't prevent boot — log and keep defaults.
            logger.exception(
                "Hydrating %s failed; falling back to defaults", package
            )
            continue
        services = getattr(app.state, package, None)
        if services is None:
            logger.warning("app.state.%s missing during hydrate — skipping", package)
            continue
        services.settings = hydrated
```

- [ ] **Step 4: Wire `hydrate_all` into the lifespan**

Modify `framework/hosting/simple_module_hosting/app_builder.py`, replace the lifespan body:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.sm.db.engine)

        # Hydrate all registered settings from DB before any module on_startup.
        from simple_module_hosting._hydrate_step import hydrate_all
        from settings.service import SettingService
        from settings.store import SettingsStore

        async with app.state.sm.db.session_factory() as session:
            store = SettingsStore(SettingService(session))
            await hydrate_all(app, store)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()
```

Check `app.state.sm.db.session_factory` vs the actual attribute name in `simple_module_db.session`. If it's a different name (e.g. `async_session_maker`), adapt the call.

- [ ] **Step 5: Run the hydration lifespan test**

Run: `uv run pytest tests/test_hydration_lifespan.py -v`
Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -x`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add framework/hosting/simple_module_hosting/_hydrate_step.py framework/hosting/simple_module_hosting/app_builder.py tests/test_hydration_lifespan.py
git commit -m "feat(hosting): hydrate module settings from DB at start of lifespan"
```

---

## Phase 3: Per-module migration

Each module: (1) drop `env_prefix`/`env_file` from its `SettingsConfigDict`, (2) refactor `register_settings` to use `register_module_settings`, (3) update tests that `monkeypatch.setenv` to use the store instead.

### Task 3.1: Migrate Settings module (itself)

**Files:**
- Modify: `modules/settings/settings/settings.py`
- Modify: `modules/settings/settings/module.py`

- [ ] **Step 1: Strip env config from `SettingsSettings`**

```python
# modules/settings/settings/settings.py
"""Settings module's own configuration (DB-backed)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsSettings(BaseSettings):
    """Configuration for the Settings module."""

    model_config = SettingsConfigDict(extra="ignore")
```

- [ ] **Step 2: Use `register_module_settings` in `SettingsModule.register_settings`**

Modify `modules/settings/settings/module.py`:

```python
    def register_settings(self, app: FastAPI) -> None:
        # The settings module itself bootstraps its own services object —
        # it can't use register_module_settings because that helper reads
        # app.state.settings.module_registry, which doesn't exist yet.
        from settings.module_registry import ModuleSettingsRegistry
        from settings.contracts.registry import SettingsRegistry
        from settings.services import SettingsServices
        from settings.settings import SettingsSettings

        services = SettingsServices(
            settings=SettingsSettings(),
            registry=SettingsRegistry(),
            module_registry=ModuleSettingsRegistry(),
        )
        setattr(app.state, MODULE_PACKAGE, services)

        # Self-register so the UI sees our own settings in the list.
        services.module_registry.register("settings", SettingsSettings)
```

- [ ] **Step 3: Run the settings module test suite**

Run: `uv run pytest modules/settings/tests/ -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add modules/settings/settings/settings.py modules/settings/settings/module.py
git commit -m "refactor(settings): move SettingsSettings off env (DB-backed) and self-register"
```

---

### Task 3.2: Migrate Users module

**Files:**
- Modify: `modules/users/users/settings.py`
- Modify: `modules/users/users/module.py`
- Modify: `modules/users/tests/test_settings.py`

- [ ] **Step 1: Strip `env_prefix` / `env_file` from `UsersSettings`**

Replace the `SettingsConfigDict` line in `modules/users/users/settings.py`:

```python
    model_config = SettingsConfigDict(extra="ignore")
```

Keep the `@model_validator` for placeholder token secrets — it now runs on DB-read (via hydrate).

- [ ] **Step 2: Update the module's `register_settings` to use the helper**

Open `modules/users/users/module.py`. Find `register_settings` and rewrite it as:

```python
    def register_settings(self, app: FastAPI) -> None:
        from users.services import UsersServices  # or whatever the dataclass is called
        from users.settings import UsersSettings
        from settings.registration import register_module_settings

        register_module_settings(
            app, "users", UsersSettings,
            lambda s: UsersServices(settings=s),
        )
```

If `UsersServices` doesn't exist as a standalone dataclass, look at the existing `register_settings` and use the same factory signature.

- [ ] **Step 3: Rewrite env-based tests in `modules/users/tests/test_settings.py`**

Every test that does `monkeypatch.setenv("SM_USERS_*", ...)` becomes: write to `SettingsStore`, call `hydrate_settings(UsersSettings, store, "users")`, assert on the result. Example:

```python
@pytest.mark.asyncio
async def test_allow_signup_override_from_db(db_session):
    from users.settings import UsersSettings
    from settings.hydrate import hydrate_settings
    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    await store.set_override("users", "allow_signup", "true", "bool")

    cfg = await hydrate_settings(UsersSettings, store, "users")
    assert cfg.allow_signup is True
```

Apply the same pattern to every env-based test in that file.

The production placeholder-secret tests still work — pass values into `UsersSettings(...)` directly, no env needed.

- [ ] **Step 4: Run the users test suite**

Run: `uv run pytest modules/users/tests/test_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full users suite**

Run: `uv run pytest modules/users/tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/users/users/settings.py modules/users/users/module.py modules/users/tests/test_settings.py
git commit -m "refactor(users): move UsersSettings off env to DB-backed"
```

---

### Task 3.3: Migrate background_tasks module

**Files:**
- Modify: `modules/background_tasks/background_tasks/settings.py`
- Modify: `modules/background_tasks/background_tasks/module.py`
- Modify: `modules/background_tasks/tests/` (any env-based tests)

- [ ] **Step 1: Strip env config + annotate `requires_restart`**

Replace the `SettingsConfigDict` line and update field definitions for Celery-critical fields:

```python
from pydantic import Field

# ...

class BackgroundTasksSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    broker_url: str = Field(
        default=DEFAULT_BROKER_URL,
        json_schema_extra={"requires_restart": True, "group": "Celery"},
    )
    result_backend: str = Field(
        default=DEFAULT_RESULT_BACKEND,
        json_schema_extra={"requires_restart": True, "group": "Celery"},
    )
    task_default_queue: str = Field(
        default=DEFAULT_QUEUE,
        json_schema_extra={"requires_restart": True, "group": "Celery"},
    )
    # rest unchanged
```

Keep the localhost-in-production validator.

- [ ] **Step 2: Update `register_settings` to use the helper**

Same pattern as Task 3.2.

- [ ] **Step 3: Update any env-based tests to write to the store**

Same pattern as Task 3.2 — apply to every `monkeypatch.setenv("SM_BG_TASKS_*", ...)` in `modules/background_tasks/tests/`.

- [ ] **Step 4: Run the background_tasks test suite**

Run: `uv run pytest modules/background_tasks/tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/background_tasks/
git commit -m "refactor(background_tasks): move settings off env; mark Celery fields requires_restart"
```

---

### Task 3.4: Migrate file_storage module

**Files:**
- Modify: `modules/file_storage/file_storage/settings.py`
- Modify: `modules/file_storage/file_storage/module.py`
- Modify: `modules/file_storage/tests/` (any env-based tests)

Same pattern as 3.2. Group S3 fields: `json_schema_extra={"group": "S3"}`. Group filesystem fields: `"group": "Filesystem"`.

- [ ] **Step 1: Strip env config; add group metadata**

```python
    model_config = SettingsConfigDict(extra="ignore")

    backend: str = constants.DEFAULT_BACKEND
    fs_root_path: str = Field(default=constants.DEFAULT_FS_ROOT, json_schema_extra={"group": "Filesystem"})
    s3_bucket: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_region: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_access_key_id: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_secret_access_key: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_endpoint_url: str = Field(default="", json_schema_extra={"group": "S3"})
    s3_presign_ttl_seconds: int = Field(default=constants.DEFAULT_PRESIGN_TTL_SECONDS, json_schema_extra={"group": "S3"})
```

- [ ] **Step 2: Update `register_settings` to use the helper**

Same pattern as 3.2.

- [ ] **Step 3: Update env-based tests**

Same pattern as 3.2.

- [ ] **Step 4: Run tests**

Run: `uv run pytest modules/file_storage/tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/file_storage/
git commit -m "refactor(file_storage): move settings off env; group fields by backend"
```

---

### Task 3.5: Migrate datasets module

Same pattern — tiny surface.

**Files:**
- Modify: `modules/datasets/datasets/settings.py`
- Modify: `modules/datasets/datasets/module.py`
- Modify: `modules/datasets/tests/` if any env-based tests exist

- [ ] **Step 1: Strip env config**

```python
    model_config = SettingsConfigDict(extra="ignore")
```

- [ ] **Step 2: Update `register_settings`**

Same pattern.

- [ ] **Step 3: Update env-based tests (if any)**

- [ ] **Step 4: Run**

Run: `uv run pytest modules/datasets/tests/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/datasets/
git commit -m "refactor(datasets): move settings off env (DB-backed)"
```

---

### Task 3.6: Full suite check after migrations

- [ ] **Step 1: Run entire test suite**

Run: `make test`
Expected: PASS.

- [ ] **Step 2: Run lint**

Run: `make lint`
Expected: PASS.

- [ ] **Step 3: Run doctor**

Run: `make doctor`
Expected: PASS (no new diagnostic errors).

If anything breaks in consumer modules (code that used `SM_<MODULE>_*` at import time), fix those sites: read from `app.state.<package>.settings.<field>` instead.

---

## Phase 4: API endpoints for module settings

### Task 4.1: Extend `_module_settings.py` with field-type and group metadata

**Files:**
- Modify: `modules/settings/settings/_module_settings.py`
- Modify: `modules/settings/tests/test_module_settings.py` (or create)

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_module_settings.py
from __future__ import annotations

from fastapi import FastAPI
from pydantic import Field
from pydantic_settings import BaseSettings
from simple_module_core.services import Services

from settings.services import SettingsServices
from settings.settings import SettingsSettings
from settings._module_settings import collect_module_settings


class _DemoCfg(BaseSettings):
    allow: bool = False
    port: int = Field(default=25, json_schema_extra={"requires_restart": True, "group": "SMTP"})
    host: str = Field(default="localhost", json_schema_extra={"group": "SMTP"})
    secret: str = ""  # name implies secret — must be masked


def test_collect_exposes_type_requires_restart_group():
    app = FastAPI()
    app.state.settings = SettingsServices(settings=SettingsSettings())
    app.state.settings.module_registry.register("demo", _DemoCfg)

    class _DemoServices:
        settings = _DemoCfg()

    app.state.demo = _DemoServices()
    app.state.sm = Services(
        settings=None, db=None, event_bus=None, menu_registry=None,
        permissions=None, feature_flags=None, health_registry=None,
        i18n_registry=None, inertia_config=None, modules=(),
    )

    views = collect_module_settings(app)
    demo = next(v for v in views if v.package == "demo")
    by_name = {f.name: f for f in demo.fields}
    assert by_name["allow"].type == "bool"
    assert by_name["port"].type == "int"
    assert by_name["port"].requires_restart is True
    assert by_name["port"].group == "SMTP"
    assert by_name["host"].group == "SMTP"
    assert by_name["allow"].group is None
    assert by_name["secret"].is_secret is True
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_module_settings.py -v`
Expected: FAIL — `type` / `requires_restart` / `group` attributes don't exist on `ModuleSettingField`.

- [ ] **Step 3: Add the metadata to `ModuleSettingField` + extractor**

In `modules/settings/settings/_module_settings.py`, extend the dataclass:

```python
@dataclass(frozen=True, slots=True)
class ModuleSettingField:
    name: str
    env_var: str
    value: Any
    default: Any
    description: str
    is_secret: bool
    type: str  # one of "bool" | "int" | "float" | "string" | "json"
    requires_restart: bool
    group: str | None
```

Extend `_field_view` to read the type (via `value_type_for_field` from `hydrate.py`) and the `json_schema_extra` on the FieldInfo:

```python
from settings.hydrate import value_type_for_field

def _field_view(name: str, settings: BaseSettings, prefix: str) -> ModuleSettingField:
    info = type(settings).model_fields[name]
    raw_value = getattr(settings, name)
    is_secret = bool(_SECRET_PATTERNS.search(name))
    extra = info.json_schema_extra or {}
    if not isinstance(extra, dict):
        extra = {}
    return ModuleSettingField(
        name=name,
        env_var=f"{prefix}{name.upper()}" if prefix else "",
        value=_mask(raw_value) if is_secret else raw_value,
        default=_mask(info.default) if is_secret else info.default,
        description=info.description or "",
        is_secret=is_secret,
        type=value_type_for_field(type(settings), name),
        requires_restart=bool(extra.get("requires_restart", False)),
        group=extra.get("group"),
    )
```

Update `serialize` to include the new keys.

- [ ] **Step 4: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_module_settings.py -v`
Expected: PASS.

- [ ] **Step 5: Verify file is still under the 300-line cap**

Run: `uv run python scripts/check_file_size.py modules/settings/settings/_module_settings.py`
Expected: under 300 lines.

- [ ] **Step 6: Commit**

```bash
git add modules/settings/settings/_module_settings.py modules/settings/tests/test_module_settings.py
git commit -m "feat(settings): expose type, requires_restart, group on module setting fields"
```

---

### Task 4.2: GET/PUT/DELETE endpoints for module settings

**Files:**
- Create: `modules/settings/settings/endpoints/module_api.py`
- Modify: `modules/settings/settings/module.py` (include router)
- Test: `modules/settings/tests/test_module_api.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_module_api.py
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_modules_returns_registered_packages(authenticated_client):
    resp = await authenticated_client.get("/api/settings/modules")
    assert resp.status_code == 200
    payload = resp.json()
    packages = {m["package"] for m in payload["modules"]}
    # The settings module registers itself; host is registered too.
    assert {"settings", "host"} <= packages


@pytest.mark.asyncio
async def test_put_module_setting_persists_and_hot_reloads(authenticated_client, app):
    resp = await authenticated_client.put(
        "/api/settings/modules/host",
        json={"multi_tenant": True},
    )
    assert resp.status_code == 200, resp.text
    assert app.state.host.settings.multi_tenant is True


@pytest.mark.asyncio
async def test_put_validation_error_surfaces_422(authenticated_client, app):
    # i18n_default_locale must be in i18n_supported_locales
    resp = await authenticated_client.put(
        "/api/settings/modules/host",
        json={"i18n_default_locale": "de"},  # supported only has "en" by default
    )
    assert resp.status_code == 422
    assert "i18n_default_locale" in resp.text


@pytest.mark.asyncio
async def test_delete_field_resets_to_default(authenticated_client, app):
    await authenticated_client.put(
        "/api/settings/modules/host", json={"multi_tenant": True}
    )
    assert app.state.host.settings.multi_tenant is True

    resp = await authenticated_client.delete(
        "/api/settings/modules/host/multi_tenant"
    )
    assert resp.status_code == 204
    assert app.state.host.settings.multi_tenant is False  # back to default


@pytest.mark.asyncio
async def test_put_secret_mask_sentinel_is_noop(authenticated_client, app):
    # First set a real value
    await authenticated_client.put(
        "/api/settings/modules/users",
        json={"reset_password_token_secret": "real-secret-value-48-chars-long-xxxxxxxxxx"},
    )
    original = app.state.users.settings.reset_password_token_secret

    # Submitting the mask sentinel should not change it
    resp = await authenticated_client.put(
        "/api/settings/modules/users",
        json={"reset_password_token_secret": "••••••••"},
    )
    assert resp.status_code == 200
    assert app.state.users.settings.reset_password_token_secret == original
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_module_api.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Implement the endpoints**

```python
# modules/settings/settings/endpoints/module_api.py
"""REST endpoints for the typed per-module settings UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from settings._module_settings import collect_module_settings, serialize
from settings.constants import MODULE_PACKAGE
from settings.deps import get_setting_service
from settings.reload import apply_changes_and_reload
from settings.service import SettingService
from settings.store import SettingsStore

_MASK_SENTINEL = "••••••••"

router = APIRouter(prefix="/modules", tags=["Settings Modules"])


@router.get("")
async def list_modules(request: Request) -> dict[str, Any]:
    """Return every registered module's current hydrated settings + metadata."""
    views = collect_module_settings(request.app)
    return {"modules": serialize(views)}


@router.put("/{package}")
async def update_module(
    package: str,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> dict[str, Any]:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")

    # Strip secret mask sentinels — treated as "no change".
    registry = getattr(request.app.state, MODULE_PACKAGE).module_registry
    cls = registry.get(package)
    if cls is None:
        raise HTTPException(404, f"Unknown module: {package}")

    from settings._module_settings import _SECRET_PATTERNS  # reuse secret regex
    cleaned = {
        k: v for k, v in body.items()
        if not (_SECRET_PATTERNS.search(k) and v == _MASK_SENTINEL)
    }
    if not cleaned:
        return {"ok": True, "changed": []}

    bus = request.app.state.sm.event_bus
    store = SettingsStore(service)
    try:
        updated = await apply_changes_and_reload(
            request.app, bus, store, package=package, changes=cleaned
        )
    except ValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc
    except KeyError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    return {"ok": True, "changed": sorted(cleaned)}


@router.delete("/{package}/{field}", status_code=204)
async def reset_field(
    package: str,
    field: str,
    request: Request,
    service: SettingService = Depends(get_setting_service),
) -> None:
    registry = getattr(request.app.state, MODULE_PACKAGE).module_registry
    cls = registry.get(package)
    if cls is None:
        raise HTTPException(404, f"Unknown module: {package}")
    if field not in cls.model_fields:
        raise HTTPException(404, f"Unknown field: {field}")

    store = SettingsStore(service)
    await store.clear_override(package, field)

    # Re-hydrate from DB (now missing the override) and reassign.
    from settings.hydrate import hydrate_settings
    hydrated = await hydrate_settings(cls, store, package)
    services = getattr(request.app.state, package)
    services.settings = hydrated

    from settings.contracts.events import SettingsReloaded
    await request.app.state.sm.event_bus.publish(
        SettingsReloaded(package=package, changed=(field,))
    )
```

- [ ] **Step 4: Include the router in `settings/module.py`**

In `SettingsModule.register_routes`:

```python
        from settings.endpoints.api import router as api
        from settings.endpoints.module_api import router as module_api
        from settings.endpoints.views import router as views

        api_router.include_router(api)
        api_router.include_router(module_api)
        view_router.include_router(views)
```

- [ ] **Step 5: Run and confirm pass**

Run: `uv run pytest modules/settings/tests/test_module_api.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add modules/settings/settings/endpoints/module_api.py modules/settings/settings/module.py modules/settings/tests/test_module_api.py
git commit -m "feat(settings): add GET/PUT/DELETE endpoints for per-module settings"
```

---

## Phase 5: Admin UI — sidebar + main panel

### Task 5.1: View endpoint returns serialized modules

**Files:**
- Modify: `modules/settings/settings/endpoints/views.py`

The existing `modules_view` already calls `collect_module_settings`. It now serves the new editable page component. Rename the component to `Settings/ModulesEdit` to keep the old read-only `Settings/Modules` around during transition (we delete it at the end of Phase 5).

- [ ] **Step 1: Add a new PAGE constant**

In `modules/settings/settings/constants.py`:

```python
PAGE_MODULES_EDIT: Final = f"{MODULE_NAME}/ModulesEdit"
```

- [ ] **Step 2: Update `modules_view`**

```python
@router.get(VIEW_MODULES_PATH, response_model=None)
async def modules_view(request: Request, inertia: InertiaDep) -> InertiaResponse:
    views = collect_module_settings(request.app)
    return await inertia.render(
        "Settings/ModulesEdit",
        {PROP_MODULES: serialize(views)},
    )
```

- [ ] **Step 3: Commit the string change now (the page file comes next)**

```bash
git add modules/settings/settings/constants.py modules/settings/settings/endpoints/views.py
git commit -m "chore(settings): point /settings/modules view at ModulesEdit page (pending)"
```

Note: build will fail until Task 5.2 lands — keep both commits close together.

---

### Task 5.2: `FieldInput` component — type-driven input

**Files:**
- Create: `modules/settings/settings/pages/components/FieldInput.tsx`
- Test: `modules/settings/pages/components/FieldInput.test.tsx` (if JS tests exist in module — otherwise cover in the integration test)

- [ ] **Step 1: Implement the component**

```tsx
// modules/settings/settings/pages/components/FieldInput.tsx
import { useState } from 'react';

export type FieldType = 'bool' | 'int' | 'float' | 'string' | 'json';

export type FieldMeta = {
  name: string;
  type: FieldType;
  value: unknown;
  default: unknown;
  description: string;
  is_secret: boolean;
  requires_restart: boolean;
  group: string | null;
  env_var: string;
};

type Props = {
  field: FieldMeta;
  onChange: (name: string, value: unknown) => void;
  value: unknown;
};

export function FieldInput({ field, onChange, value }: Props) {
  const [revealed, setRevealed] = useState(false);

  if (field.is_secret && !revealed) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="password"
          value="••••••••"
          readOnly
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
        <button
          type="button"
          className="text-sm text-primary hover:underline"
          onClick={() => {
            setRevealed(true);
            onChange(field.name, ''); // start blank
          }}
        >
          Set new value
        </button>
      </div>
    );
  }

  switch (field.type) {
    case 'bool':
      return (
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(field.name, e.target.checked)}
        />
      );
    case 'int':
      return (
        <input
          type="number"
          step="1"
          value={String(value ?? '')}
          onChange={(e) => onChange(field.name, e.target.value === '' ? null : Number(e.target.value))}
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
      );
    case 'float':
      return (
        <input
          type="number"
          step="any"
          value={String(value ?? '')}
          onChange={(e) => onChange(field.name, e.target.value === '' ? null : Number(e.target.value))}
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
      );
    case 'json':
      return (
        <textarea
          rows={3}
          value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
          onChange={(e) => onChange(field.name, e.target.value)}
          className="w-full rounded border px-2 py-1 font-mono text-xs"
        />
      );
    default:
      return (
        <input
          type="text"
          value={String(value ?? '')}
          onChange={(e) => onChange(field.name, e.target.value)}
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
      );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/settings/settings/pages/components/FieldInput.tsx
git commit -m "feat(settings-ui): add FieldInput component with type-driven rendering"
```

---

### Task 5.3: `ModuleForm` component

**Files:**
- Create: `modules/settings/settings/pages/components/ModuleForm.tsx`

- [ ] **Step 1: Implement**

```tsx
// modules/settings/settings/pages/components/ModuleForm.tsx
import { router } from '@inertiajs/react';
import { useMemo, useState } from 'react';
import { FieldInput, type FieldMeta } from './FieldInput';

export type ModuleView = {
  module_name: string;
  package: string;
  env_prefix: string;
  class_name: string;
  fields: FieldMeta[];
};

type Props = { module: ModuleView };

export function ModuleForm({ module: m }: Props) {
  const initial = useMemo(() => {
    const o: Record<string, unknown> = {};
    for (const f of m.fields) o[f.name] = f.value;
    return o;
  }, [m]);

  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const dirty = JSON.stringify(values) !== JSON.stringify(initial);

  const grouped = useMemo(() => {
    const g: Record<string, FieldMeta[]> = {};
    for (const f of m.fields) {
      const key = f.group ?? 'General';
      (g[key] ??= []).push(f);
    }
    return g;
  }, [m]);

  async function onSave() {
    setBusy(true);
    setErrors({});
    const changed: Record<string, unknown> = {};
    for (const k of Object.keys(values)) {
      if (JSON.stringify(values[k]) !== JSON.stringify(initial[k])) {
        changed[k] = values[k];
      }
    }
    const resp = await fetch(`/api/settings/modules/${m.package}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changed),
    });
    if (resp.status === 422) {
      const body = await resp.json();
      const fieldErrs: Record<string, string> = {};
      for (const d of body.detail ?? []) {
        if (d.loc && d.loc.length) fieldErrs[d.loc[d.loc.length - 1]] = d.msg;
      }
      setErrors(fieldErrs);
    } else if (resp.ok) {
      router.reload({ only: ['modules'] });
    }
    setBusy(false);
  }

  async function onReset(name: string) {
    await fetch(`/api/settings/modules/${m.package}/${name}`, { method: 'DELETE' });
    router.reload({ only: ['modules'] });
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between border-b pb-3">
        <div>
          <h2 className="text-xl font-semibold">{m.module_name}</h2>
          <p className="text-xs font-mono text-muted-foreground">{m.package}</p>
        </div>
        <button
          type="button"
          disabled={!dirty || busy}
          onClick={onSave}
          className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
      </header>

      {Object.entries(grouped).map(([group, fields]) => (
        <section key={group} className="space-y-3">
          <h3 className="text-sm font-semibold text-muted-foreground">{group}</h3>
          {fields.map((f) => {
            const isModified = JSON.stringify(values[f.name]) !== JSON.stringify(f.default);
            return (
              <div key={f.name} className="grid grid-cols-[1fr_2fr] gap-4 items-start">
                <div>
                  <label className="font-mono text-xs">{f.name}</label>
                  {f.description && (
                    <p className="mt-1 text-xs text-muted-foreground">{f.description}</p>
                  )}
                  {f.requires_restart && isModified && (
                    <span className="mt-1 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase text-amber-900">
                      Requires restart
                    </span>
                  )}
                </div>
                <div>
                  <FieldInput
                    field={f}
                    value={values[f.name]}
                    onChange={(name, v) => setValues((prev) => ({ ...prev, [name]: v }))}
                  />
                  {isModified && (
                    <button
                      type="button"
                      onClick={() => onReset(f.name)}
                      className="mt-1 text-xs text-primary hover:underline"
                    >
                      Reset to default
                    </button>
                  )}
                  {errors[f.name] && (
                    <p className="mt-1 text-xs text-red-600">{errors[f.name]}</p>
                  )}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/settings/settings/pages/components/ModuleForm.tsx
git commit -m "feat(settings-ui): add ModuleForm with typed inputs, grouping, reset, validation"
```

---

### Task 5.4: `ModulesEdit` page — sidebar layout

**Files:**
- Create: `modules/settings/settings/pages/ModulesEdit.tsx`

- [ ] **Step 1: Implement**

```tsx
// modules/settings/settings/pages/ModulesEdit.tsx
import { keys, useT } from '@simple-module/i18n';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { useMemo, useState } from 'react';
import type React from 'react';
import { ModuleForm, type ModuleView } from './components/ModuleForm';
import { ROUTES } from './routes';

type Props = { modules: ModuleView[] };

function ModulesEdit({ modules }: Props) {
  const { t } = useT();
  const [selected, setSelected] = useState(modules[0]?.package);
  const [q, setQ] = useState('');

  const filtered = useMemo(() => {
    if (!q) return modules;
    const query = q.toLowerCase();
    return modules.filter(
      (m) =>
        m.module_name.toLowerCase().includes(query) ||
        m.package.toLowerCase().includes(query) ||
        m.fields.some((f) => f.name.toLowerCase().includes(query))
    );
  }, [modules, q]);

  const current = modules.find((m) => m.package === selected);

  return (
    <div className="flex h-[calc(100vh-64px)]">
      <aside className="w-64 border-r bg-muted/40 p-3 overflow-y-auto">
        <input
          type="text"
          placeholder={t(keys.settings.modules.search_placeholder)}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="mb-3 w-full rounded border px-2 py-1 text-sm"
        />
        <nav className="space-y-1">
          {filtered.map((m) => (
            <button
              key={m.package}
              type="button"
              onClick={() => setSelected(m.package)}
              className={`block w-full rounded px-3 py-2 text-left text-sm ${
                m.package === selected
                  ? 'bg-primary text-primary-foreground'
                  : 'hover:bg-muted'
              }`}
            >
              <div className="font-medium">{m.module_name}</div>
              <div className="text-xs opacity-70">
                {m.fields.length} {t(keys.settings.modules.field_count_suffix)}
              </div>
            </button>
          ))}
        </nav>
        <div className="mt-4 border-t pt-3 text-xs">
          <a href={ROUTES.browse} className="text-primary hover:underline">
            {t(keys.settings.modules.browse_free_form_link)}
          </a>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto p-6">
        {current ? (
          <ModuleForm module={current} />
        ) : (
          <p className="text-muted-foreground">
            {t(keys.settings.modules.empty_title)}
          </p>
        )}
      </main>
    </div>
  );
}

ModulesEdit.layout = (page: React.ReactNode) => (
  <AuthenticatedLayout>{page}</AuthenticatedLayout>
);
export default ModulesEdit;
```

- [ ] **Step 2: Add the required i18n keys**

In `modules/settings/settings/locales/en.json`, under the existing `"modules"` object, add:

```json
"search_placeholder": "Search modules or fields…",
"field_count_suffix": "fields",
"browse_free_form_link": "View free-form settings"
```

And the equivalent keys in other locale files (copy from `en.json` and translate or leave the English as a placeholder).

- [ ] **Step 3: Commit**

```bash
git add modules/settings/settings/pages/ModulesEdit.tsx modules/settings/settings/locales/
git commit -m "feat(settings-ui): add ModulesEdit page (sidebar + main panel layout)"
```

---

### Task 5.5: Delete the old read-only `Modules.tsx`

- [ ] **Step 1: Remove the old page**

```bash
git rm modules/settings/settings/pages/Modules.tsx
```

- [ ] **Step 2: Remove the old PAGE constant and any references**

In `modules/settings/settings/constants.py`, drop `PAGE_MODULES` if nothing else references it (grep first).

- [ ] **Step 3: Run `make gen-pages` and restart dev**

Run: `make gen-pages`

- [ ] **Step 4: Run make lint + doctor**

Run: `make lint && make doctor`
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

Start `make dev`, visit `http://localhost:8000/settings/modules`, verify sidebar renders with modules, clicking one shows fields, toggling `host.multi_tenant` saves.

- [ ] **Step 6: Commit**

```bash
git add modules/settings/settings/constants.py
git commit -m "chore(settings): remove read-only Modules page (replaced by ModulesEdit)"
```

---

### Task 5.6: E2E test

**Files:**
- Create: `tests/e2e/test_settings_ui.py`

- [ ] **Step 1: Write the E2E test**

```python
# tests/e2e/test_settings_ui.py
import pytest
from playwright.async_api import async_playwright


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_toggle_setting_takes_effect_without_restart(live_server, admin_cookie):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        await context.add_cookies([admin_cookie])
        page = await context.new_page()

        await page.goto(f"{live_server}/settings/modules")
        await page.click("text=Users")
        await page.check('input[type=checkbox]:near(:text("allow_signup"))')
        await page.click('button:has-text("Save")')
        await page.wait_for_load_state("networkidle")

        # allow_signup=true means /users/register is reachable
        await page.goto(f"{live_server}/users/register")
        assert "Register" in await page.title() or 200 == page.response.status
```

- [ ] **Step 2: Run (requires `make dev` + playwright chromium installed)**

Run: `make test-e2e`
Expected: PASS.

If the test fails because of selector brittleness, refine selectors — the point is to verify hot-reload end-to-end.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/test_settings_ui.py
git commit -m "test(e2e): verify settings-UI hot-reload for users.allow_signup"
```

---

## Phase 6: Import-from-env CLI

### Task 6.1: `smpy settings import-from-env` command

**Files:**
- Modify: `modules/settings/settings/cli.py` (create if missing; check `pyproject.toml` for existing entry point)
- Modify: `modules/settings/pyproject.toml` (add `[project.scripts]` entry)
- Test: `modules/settings/tests/test_cli_import.py`

- [ ] **Step 1: Write the failing test**

```python
# modules/settings/tests/test_cli_import.py
from __future__ import annotations

import pytest

from settings.cli import import_from_env_impl


@pytest.mark.asyncio
async def test_import_from_env_writes_overrides(db_session, monkeypatch, app):
    monkeypatch.setenv("SM_USERS_ALLOW_SIGNUP", "true")
    monkeypatch.setenv("SM_USERS_SMTP_PORT", "2525")
    monkeypatch.setenv("SM_BG_TASKS_RETENTION_DAYS", "30")

    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)

    users = await store.get_overrides("users")
    bg = await store.get_overrides("background_tasks")
    assert users["allow_signup"] == ("true", "bool")
    assert users["smtp_port"] == ("2525", "int")
    assert bg["retention_days"] == ("30", "int")
    assert n == 3


@pytest.mark.asyncio
async def test_import_ignores_unknown_env(db_session, monkeypatch, app):
    monkeypatch.setenv("SM_USERS_DOES_NOT_EXIST", "value")

    from settings.service import SettingService
    from settings.store import SettingsStore

    store = SettingsStore(SettingService(db_session))
    n = await import_from_env_impl(app, store)
    assert n == 0
    assert await store.get_overrides("users") == {}
```

- [ ] **Step 2: Run and confirm failure**

Run: `uv run pytest modules/settings/tests/test_cli_import.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement the CLI impl**

```python
# modules/settings/settings/cli.py
"""CLI entry points for the Settings module.

``smpy settings import-from-env`` — reads every ``SM_<MODULE>_*`` from the
current process environment and writes each matching field as an override
to the ``Setting`` table. Idempotent.
"""

from __future__ import annotations

import asyncio
import os
import sys

from fastapi import FastAPI

from settings.constants import MODULE_PACKAGE
from settings.hydrate import value_type_for_field
from settings.store import SettingsStore


def _env_prefix_for(package: str) -> str:
    if package == "background_tasks":
        return "SM_BG_TASKS_"
    if package == "file_storage":
        return "SM_FILE_STORAGE_"
    if package == "host":
        return "SM_"  # careful — host catches many vars
    return f"SM_{package.upper()}_"


async def import_from_env_impl(app: FastAPI, store: SettingsStore) -> int:
    """Read env vars matching each registered module's prefix; write overrides.

    Returns the number of overrides written.
    """
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    count = 0
    for package, cls in registry.items():
        prefix = _env_prefix_for(package)
        for field_name in cls.model_fields:
            env_name = f"{prefix}{field_name.upper()}"
            if env_name not in os.environ:
                continue
            raw = os.environ[env_name]
            vtype = value_type_for_field(cls, field_name)
            await store.set_override(package, field_name, raw, vtype)
            count += 1
    return count


def main() -> int:
    """Entry point — builds a temporary app to read the registry, then imports."""
    from simple_module_hosting.app_builder import create_app
    from settings.service import SettingService

    app = create_app()

    async def run():
        async with app.state.sm.db.session_factory() as session:
            store = SettingsStore(SettingService(session))
            n = await import_from_env_impl(app, store)
            await session.commit()
            print(f"Imported {n} override(s) from environment.")
            return 0

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Register the CLI in `modules/settings/pyproject.toml`**

Add under `[project.scripts]`:

```toml
[project.scripts]
smpy settings = "settings.cli:main"
```

(If `[project.scripts]` already exists, append the entry.)

- [ ] **Step 5: Reinstall workspace so the CLI is discoverable**

Run: `uv sync --all-packages`

- [ ] **Step 6: Run the CLI test**

Run: `uv run pytest modules/settings/tests/test_cli_import.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add modules/settings/settings/cli.py modules/settings/pyproject.toml modules/settings/tests/test_cli_import.py
git commit -m "feat(settings): add smpy settings import-from-env CLI"
```

---

## Phase 7: Cleanup — `.env.example`, compose, README

### Task 7.1: Shrink `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Replace with the bootstrap-only example**

```bash
# .env.example
# Only SM_DATABASE_URL is required. Everything else has sensible defaults.
# All module-level settings (SMTP, Celery, users, etc.) are now managed in
# the admin UI at /settings/modules — no env vars needed.

# Database (required)
SM_DATABASE_URL=sqlite+aiosqlite:///./app.db
# SM_DATABASE_URL=postgresql+asyncpg://sm:sm@localhost:5432/simple_module

# Process identity (production must override SM_SECRET_KEY)
SM_ENVIRONMENT=development
SM_SECRET_KEY=change-me-in-production

# Dev-only: Vite asset URL (ignored in production builds)
SM_VITE_DEV_URL=http://localhost:5050
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: shrink .env.example to bootstrap-only (DB, environment, secret, vite)"
```

---

### Task 7.2: Update `docker-compose.yml`

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Remove `SM_BG_TASKS_*` env entries**

The compose file currently sets `SM_BG_TASKS_BROKER_URL=redis://redis:6379/0` etc. Update `BackgroundTasksSettings` defaults in Task 3.3 so `broker_url` defaults to `redis://redis:6379/0` — this way dev-compose works from defaults. Then delete the compose env lines.

Inspect `docker-compose.yml:36-40` and `docker-compose.yml:61-65` and remove the `SM_BG_TASKS_*` env entries. Keep `SM_DATABASE_URL`.

Actually: the compose defaults must match the service hostnames (`redis`), which differ from local dev (`localhost`). Two options:
- **Option A** — keep env override in compose. Reasonable compromise; compose is "deployment", not module config.
- **Option B** — change Celery defaults to `redis://redis:6379/*` and tell local-dev users to override via `smpy settings` CLI after first boot.

Pick **A** — compose env stays. The spec's promise ("only DB URL in env") refers to the user's local `.env.example`, not CI/compose overrides which are container-specific plumbing.

So: **no changes to `docker-compose.yml`** for this task. Document the exception:

- [ ] **Step 2: Document the compose exception in README**

Done in Task 7.3.

- [ ] **Step 3: No commit needed for this task**

---

### Task 7.3: Rewrite README env-var section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the env-var table**

Replace the existing env-var table (around `README.md:95-106`) with:

```markdown
## Configuration

Local deployments only need one env var — everything else has sensible defaults and is managed in the admin UI at `/settings/modules`.

| Variable | Default | Required |
|---|---|---|
| `SM_DATABASE_URL` | `sqlite+aiosqlite:///./app.db` | Yes — async URL. Postgres: `postgresql+asyncpg://...` |
| `SM_ENVIRONMENT` | `development` | No — any value other than `development`, `test`, `testing` triggers strict discovery and placeholder-secret checks |
| `SM_SECRET_KEY` | `change-me-in-production` | No in dev; **must** be overridden in production |
| `SM_VITE_DEV_URL` | `http://localhost:5050` | Dev only |

Power users can still override the following bootstrap knobs via env if needed: `SM_DB_POOL_SIZE`, `SM_DB_MAX_OVERFLOW`, `SM_DB_POOL_PRE_PING`, `SM_DB_POOL_RECYCLE`, `SM_DEBUG`, `SM_LOG_LEVEL`, `SM_LOG_FORMAT`, `SM_MODULES_ENABLED`. These are needed before the DB connection is open.

All module-level settings — users, SMTP, Celery broker, file storage backend, etc. — live in the admin UI. After upgrading an existing deployment, run once:

```bash
uv run smpy settings import-from-env
```

to seed DB overrides from the current `SM_*` environment.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README config section — bootstrap vars only + UI pointer"
```

---

## Phase 8: Final verification

### Task 8.1: Full lint + tests + doctor

- [ ] **Step 1: Run the full pipeline**

Run: `make lint && make test && make doctor`
Expected: all PASS.

- [ ] **Step 2: Check 300-line cap on touched files**

Run: `uv run python scripts/check_file_size.py`
Expected: PASS.

- [ ] **Step 3: Manual smoke test**

Start `make dev`. Visit `/settings/modules`. Verify:
- Sidebar shows `Users`, `Background Tasks`, `Datasets`, `File Storage`, `Settings`, `Host`.
- Clicking `Users` shows fields grouped by `SMTP`, `General`, etc.
- Toggling `allow_signup` → Save → no reload needed → `/users/register` reachable.
- Editing `broker_url` shows "Requires restart" badge once the value differs from live.
- Editing a secret field replaces the mask with a blank input.
- "Reset to default" appears when a field differs from its pydantic default; clicking it removes the DB row.

### Task 8.2: Write release note snippet

**Files:**
- Create: `docs/release-notes/2026-04-21-db-backed-settings.md`

- [ ] **Step 1: Write the note**

```markdown
# DB-backed module settings

Every `SM_<MODULE>_*` env var has moved to the admin UI at `/settings/modules`.
`.env` now only needs `SM_DATABASE_URL` in typical deployments.

## Upgrading

After deploying this release:

1. Run `uv run smpy settings import-from-env` once to seed the DB with your current environment values.
2. Remove the `SM_<MODULE>_*` entries from your `.env` / deployment config (they're no longer read).

## Breaking changes

Setting `SM_USERS_ALLOW_SIGNUP=true` (or any other `SM_<MODULE>_*`) in the environment no longer has any effect. Use the admin UI or the `smpy settings` CLI.
```

- [ ] **Step 2: Commit**

```bash
git add docs/release-notes/2026-04-21-db-backed-settings.md
git commit -m "docs: add release note for DB-backed module settings"
```

---

## Final commit and PR

- [ ] **Step 1: Double-check everything is committed**

Run: `git status`
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Run the full test suite one more time**

Run: `make test && make lint && make doctor`
Expected: PASS.

- [ ] **Step 3: Push and open PR (only if the user has asked for a PR)**

Do not push or open a PR unless the user explicitly requests it.

---

## Appendix — open decisions carried from the spec

These were marked "open decisions to resolve during plan writing" in the spec. Resolutions baked into the tasks above:

1. **Metadata shape**: chose plain `Field(..., json_schema_extra={"requires_restart": True, "group": "SMTP"})` — no new helper function. Keeps module code readable and avoids yet another API to learn.

2. **Event bus sync/async**: `EventBus.publish` is async (uses `asyncio.gather`). `apply_changes_and_reload` `await`s the publish so handlers run before the API responds.

3. **`list_packages` source**: uses the in-memory registry (`ModuleSettingsRegistry.all_packages()`) as the source of truth during the app's lifetime. A separate `smpy settings prune-orphans` command (future follow-up, not in this plan) would scan the DB for `Setting` rows whose package is no longer registered.
