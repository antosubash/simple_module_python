# Alembic Database Migrations — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace auto-`create_all` in module startup with Alembic-managed schema versioning, add migration diagnostics, and extend the health endpoint with migration status.

**Architecture:** Alembic config lives in `host/` alongside the app entry point. `env.py` reuses entry-point discovery via `discover_modules()` to collect all module metadata automatically. A startup migration check in the app lifespan raises `RuntimeError` if the DB isn't at head. Four diagnostic additions integrate into the existing `run_diagnostics()` system and `/health` endpoint.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, Alembic 1.14+, FastAPI, pytest-asyncio

**Design doc:** `docs/plans/2026-04-13-alembic-migrations-design.md`

---

### Task 1: Create `alembic.ini` in `host/`

**Files:**
- Create: `host/alembic.ini`

**Step 1: Create the Alembic config file**

```ini
[alembic]
script_location = migrations
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Note: `sqlalchemy.url` is intentionally empty — `env.py` sets it from `Settings.database_url`.

**Step 2: Verify the file parses**

Run: `cd host && python -c "from alembic.config import Config; c = Config('alembic.ini'); print('script_location:', c.get_main_option('script_location'))"`
Expected: `script_location: migrations`

**Step 3: Commit**

```bash
git add host/alembic.ini
git commit -m "feat: add alembic.ini in host/ with empty sqlalchemy.url"
```

---

### Task 2: Create `host/migrations/script.py.mako`

**Files:**
- Create: `host/migrations/script.py.mako`

**Step 1: Create the Mako template**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

**Step 2: Create the empty `versions/` directory**

Run: `mkdir -p host/migrations/versions && touch host/migrations/versions/.gitkeep`

**Step 3: Commit**

```bash
git add host/migrations/script.py.mako host/migrations/versions/.gitkeep
git commit -m "feat: add Alembic migration template and versions directory"
```

---

### Task 3: Create `host/migrations/env.py` with discovery and filtering

**Files:**
- Create: `host/migrations/env.py`

This is the most important file — it wires Alembic to the module system.

**Step 1: Write `env.py`**

```python
"""Alembic environment — discovers module models via entry points."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases
from simple_module_hosting.settings import Settings
from sqlalchemy import MetaData, engine_from_config, pool

logger = logging.getLogger("alembic.env")

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Discover module models ──────────────────────────────────────────
# discover_modules() loads entry points, which import module packages,
# which call create_module_base() and define SQLAlchemy models.
# After this, all_module_bases contains every module's DeclarativeBase.
discover_modules()

# Combine all module metadata into a single MetaData for autogenerate
target_metadata = MetaData()
for base in all_module_bases:
    for table in base.metadata.tables.values():
        table.tometadata(target_metadata)

# Allowlist: only manage tables declared by modules
MODULE_TABLES = {t.name for t in target_metadata.tables.values()}


def include_object(object, name, type_, reflected, compare_to):
    """Filter autogenerate to only module-declared tables."""
    if type_ == "table":
        return name in MODULE_TABLES
    if hasattr(object, "table"):
        return object.table.name in MODULE_TABLES
    return True


def _get_url() -> str:
    """Read database URL from settings, convert async to sync driver."""
    settings = Settings()
    url = settings.database_url
    url = url.replace("+aiosqlite", "")
    url = url.replace("+asyncpg", "+psycopg2")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a live DB."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 2: Verify env.py imports cleanly**

Run: `cd host && python -c "import migrations.env; print('OK')" 2>&1 || echo "Import check skipped (expected outside alembic context)"`

Note: This may fail outside the Alembic CLI context because `context.config` isn't set. That's expected — the real test is in Task 4.

**Step 3: Commit**

```bash
git add host/migrations/env.py
git commit -m "feat: add Alembic env.py with entry-point discovery and table filtering"
```

---

### Task 4: Generate the initial migration and verify

**Files:**
- Creates: `host/migrations/versions/<hash>_initial_schema.py` (auto-generated)

**Step 1: Generate the initial migration**

Run: `cd host && uv run alembic revision --autogenerate -m "initial schema"`
Expected: Creates a file in `host/migrations/versions/` with `create_table` for `products_product`.

**Step 2: Inspect the generated migration**

Read the generated file and verify:
- It contains `op.create_table('products_product', ...)` with all columns (id, name, description, price, is_active, created_at, updated_at, created_by, updated_by).
- The `downgrade` contains `op.drop_table('products_product')`.
- No unexpected tables appear (no DROP for non-module tables).

**Step 3: Run the migration against a fresh SQLite DB**

Run: `cd host && SM_DATABASE_URL=sqlite:///./test_migrate.db uv run alembic upgrade head && rm -f test_migrate.db`
Expected: Exits cleanly with "Running upgrade ... -> ..., initial schema"

**Step 4: Commit**

```bash
git add host/migrations/versions/
git commit -m "feat: add initial schema migration for products module"
```

---

### Task 5: Add `MigrationState` dataclass and startup check to `app_builder.py`

**Files:**
- Modify: `framework/hosting/src/simple_module_hosting/app_builder.py:1-15` (imports), `:88-94` (lifespan)

**Step 1: Write the failing test**

Add to `framework/hosting/tests/test_app.py`:

```python
class TestMigrationCheck:
    async def test_app_state_has_migration_info(self, app: FastAPI):
        """App state should include migration status after startup."""
        assert hasattr(app.state, "migration")
        migration = app.state.migration
        assert "current_revision" in migration
        assert "head_revision" in migration
        assert "is_current" in migration
        assert "pending_count" in migration
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_app.py::TestMigrationCheck -v`
Expected: FAIL — `app.state` has no attribute `migration`

**Step 3: Add imports and `_check_migrations` to `app_builder.py`**

Add these imports near the top of `app_builder.py` (after existing imports, around line 15):

```python
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
```

Add this function before `create_app`:

```python
async def _check_migrations(engine, alembic_ini_path: str = "host/alembic.ini") -> dict:
    """Check database migration state. Raises RuntimeError if not at head.

    Returns a dict with migration status for storage on app.state.
    """
    alembic_cfg = AlembicConfig(alembic_ini_path)
    script = ScriptDirectory.from_config(alembic_cfg)
    head = script.get_current_head()

    async with engine.connect() as conn:

        def _get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()

        current = await conn.run_sync(_get_current)

    is_current = current == head
    pending_count = 0
    if not is_current and head is not None:
        revisions = list(script.iterate_revisions(head, current))
        pending_count = len(revisions)
        raise RuntimeError(
            f"Database is {pending_count} revision(s) behind "
            f"(at {current!r}, head is {head!r}). Run: make migrate"
        )

    return {
        "current_revision": current,
        "head_revision": head,
        "is_current": is_current,
        "pending_count": pending_count,
    }
```

**Step 4: Update the lifespan in `create_app`**

Change the lifespan (lines ~88-95) from:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()
```

to:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await _check_migrations(app.state.db.engine)
        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.db.engine.dispose()
```

**Step 5: Update the test `conftest.py` for the migration check**

The `app` fixture in `conftest.py` uses `create_app()` which now runs `_check_migrations` in its lifespan. However, test apps use in-memory SQLite with no Alembic history. We need to make the migration check work in tests.

Update `_check_migrations` to handle the case where `head` is `None` (no migration scripts found from the test context) gracefully — by skipping the check and returning a "no migrations configured" state.

Update the function to add this early return after computing `head`:

```python
    # No migrations configured (e.g., test environments)
    if head is None:
        return {
            "current_revision": None,
            "head_revision": None,
            "is_current": True,
            "pending_count": 0,
        }
```

**Step 6: Run tests**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests pass including `TestMigrationCheck`

**Step 7: Commit**

```bash
git add framework/hosting/src/simple_module_hosting/app_builder.py framework/hosting/tests/test_app.py
git commit -m "feat: add startup migration check with RuntimeError on mismatch"
```

---

### Task 6: Remove `create_all` from `ProductsModule.on_startup`

**Files:**
- Modify: `modules/products/src/sm_products/module.py:57-63`

**Step 1: Write the failing test**

Add to `modules/products/tests/test_products.py` (or a new test file if more appropriate):

```python
class TestProductsModuleLifecycle:
    async def test_on_startup_does_not_call_create_all(self):
        """on_startup should not create tables — Alembic manages schema."""
        from unittest.mock import AsyncMock, MagicMock

        mod = ProductsModule()
        mock_app = MagicMock()
        mock_app.state.db.engine = AsyncMock()

        # on_startup should be a no-op (or at least not call create_all)
        await mod.on_startup(mock_app)

        # Engine should not have been used for DDL
        mock_app.state.db.engine.begin.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest modules/products/tests/test_products.py::TestProductsModuleLifecycle -v`
Expected: FAIL — `on_startup` currently calls `engine.begin()` for `create_all`

**Step 3: Remove `on_startup` from `ProductsModule`**

In `modules/products/src/sm_products/module.py`, delete the entire `on_startup` method (lines 57-63):

```python
    async def on_startup(self, app: FastAPI) -> None:
        """Ensure the products table exists (dev convenience)."""
        from sm_products.models import Base

        engine = app.state.db.engine
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
```

Also remove the unused `FastAPI` import from line 5 if it's only used by `on_startup`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest modules/products/tests/test_products.py::TestProductsModuleLifecycle -v`
Expected: PASS

**Step 5: Update `conftest.py` — tables now need Alembic or explicit setup**

The `conftest.py` `app` fixture already calls `create_all` for the Products base after `create_app()`. This must stay for tests (since tests don't run Alembic migrations). Verify:

Run: `uv run pytest -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add modules/products/src/sm_products/module.py modules/products/tests/test_products.py
git commit -m "refactor: remove create_all from ProductsModule — Alembic manages schema"
```

---

### Task 7: Extend `/health` endpoint with migration status

**Files:**
- Modify: `framework/hosting/src/simple_module_hosting/health.py:8-10`
- Modify: `framework/hosting/tests/test_app.py` (add test)

**Step 1: Write the failing test**

Add to `framework/hosting/tests/test_app.py`:

```python
class TestHealthMigrationStatus:
    async def test_health_includes_migration(self, client: httpx.AsyncClient):
        resp = await client.get("/health")
        data = resp.json()
        assert "migration" in data
        assert "current_revision" in data["migration"]
        assert "head_revision" in data["migration"]
        assert "is_current" in data["migration"]
        assert "pending_count" in data["migration"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_app.py::TestHealthMigrationStatus -v`
Expected: FAIL — `/health` returns `{"status": "healthy"}` without migration info

**Step 3: Update the health endpoint**

Replace `framework/hosting/src/simple_module_hosting/health.py`:

```python
"""Health check endpoints."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(request: Request) -> dict:
    migration = getattr(request.app.state, "migration", None)
    return {
        "status": "healthy",
        "migration": migration,
    }


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> dict:
    # TODO: check DB connectivity, module health
    return {"status": "ready"}
```

**Step 4: Run tests**

Run: `uv run pytest framework/hosting/tests/test_app.py -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add framework/hosting/src/simple_module_hosting/health.py framework/hosting/tests/test_app.py
git commit -m "feat: include migration status in /health endpoint"
```

---

### Task 8: Add migration diagnostics to `diagnostics.py`

**Files:**
- Modify: `framework/core/src/simple_module_core/diagnostics.py:229-231` (update `run_diagnostics`)
- Modify: `framework/core/tests/test_core.py` (add tests)

**Step 1: Write the failing tests**

Add to `framework/core/tests/test_core.py`:

```python
class TestMigrationDiagnostics:
    async def test_sm009_migration_mismatch(self):
        """SM009 should fire when current revision != head."""
        from simple_module_core.diagnostics import MigrationDiagnostics, DiagnosticLevel

        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="def456",
        )
        assert len(results) == 1
        assert results[0].code == "SM009"
        assert results[0].level == DiagnosticLevel.ERROR

    async def test_sm009_no_error_when_current(self):
        """SM009 should not fire when DB is at head."""
        from simple_module_core.diagnostics import MigrationDiagnostics

        diag = MigrationDiagnostics()
        results = diag.check_revision_mismatch(
            current_revision="abc123",
            head_revision="abc123",
        )
        assert len(results) == 0

    async def test_sm010_missing_tables(self):
        """SM010 should fire when module tables aren't in migration tables."""
        from simple_module_core.diagnostics import MigrationDiagnostics, DiagnosticLevel

        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product", "products_category"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 1
        assert results[0].code == "SM010"
        assert results[0].level == DiagnosticLevel.WARNING
        assert "products_category" in results[0].message

    async def test_sm010_no_warning_when_covered(self):
        """SM010 should not fire when all tables are covered."""
        from simple_module_core.diagnostics import MigrationDiagnostics

        diag = MigrationDiagnostics()
        results = diag.check_table_coverage(
            module_tables={"products_product"},
            migrated_tables={"products_product"},
        )
        assert len(results) == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/core/tests/test_core.py::TestMigrationDiagnostics -v`
Expected: FAIL — `MigrationDiagnostics` does not exist

**Step 3: Add `MigrationDiagnostics` class to `diagnostics.py`**

Add before the `run_diagnostics` function (around line 228):

```python
class MigrationDiagnostics:
    """Validates database migration state."""

    def check_revision_mismatch(
        self,
        current_revision: str | None,
        head_revision: str | None,
    ) -> list[Diagnostic]:
        """SM009: Error if database is not at the migration head."""
        if current_revision == head_revision:
            return []
        return [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM009",
                message=(f"Database at revision {current_revision!r}, expected {head_revision!r}"),
                module_name="migrations",
                suggestion="Run: make migrate",
            )
        ]

    def check_table_coverage(
        self,
        module_tables: set[str],
        migrated_tables: set[str],
    ) -> list[Diagnostic]:
        """SM010: Warning if module tables are missing from migration history."""
        missing = module_tables - migrated_tables
        return [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM010",
                message=f"Table '{table}' declared in models but not found in migration history",
                module_name="migrations",
                suggestion=f'Run: make migration msg="add {table}"',
            )
            for table in sorted(missing)
        ]
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/core/tests/test_core.py::TestMigrationDiagnostics -v`
Expected: All 4 tests pass

**Step 5: Commit**

```bash
git add framework/core/src/simple_module_core/diagnostics.py framework/core/tests/test_core.py
git commit -m "feat: add MigrationDiagnostics with SM009 (revision) and SM010 (coverage)"
```

---

### Task 9: Integrate migration diagnostics into `run_diagnostics` and `app_builder`

**Files:**
- Modify: `framework/core/src/simple_module_core/diagnostics.py:229-231`
- Modify: `framework/core/src/simple_module_core/__init__.py`
- Modify: `framework/hosting/src/simple_module_hosting/app_builder.py:56-62`

**Step 1: Update `run_diagnostics` signature**

In `diagnostics.py`, change `run_diagnostics` (line ~229) from:

```python
def run_diagnostics(modules: list[ModuleBase]) -> list[Diagnostic]:
    """Convenience function to run all diagnostics."""
    return ModuleDiagnostics().run(modules)
```

to:

```python
def run_diagnostics(
    modules: list[ModuleBase],
    *,
    migration_state: dict | None = None,
    module_tables: set[str] | None = None,
    migrated_tables: set[str] | None = None,
) -> list[Diagnostic]:
    """Convenience function to run all diagnostics.

    When ``migration_state`` is provided, also runs migration diagnostics.
    """
    diagnostics = ModuleDiagnostics().run(modules)

    if migration_state is not None:
        migration_diag = MigrationDiagnostics()
        diagnostics.extend(
            migration_diag.check_revision_mismatch(
                current_revision=migration_state.get("current_revision"),
                head_revision=migration_state.get("head_revision"),
            )
        )
        if module_tables is not None and migrated_tables is not None:
            diagnostics.extend(migration_diag.check_table_coverage(module_tables, migrated_tables))

    return diagnostics
```

**Step 2: Export `MigrationDiagnostics` from `__init__.py`**

In `framework/core/src/simple_module_core/__init__.py`, add to imports:

```python
from simple_module_core.diagnostics import (
    DiagnosticLevel,
    MigrationDiagnostics,
    print_diagnostics,
    run_diagnostics,
)
```

And add `"MigrationDiagnostics"` to `__all__`.

**Step 3: Wire into `app_builder.py`**

In `app_builder.py`, update the diagnostics section (lines ~56-62) to pass migration state.

Change from:

```python
    if settings.is_development:
        diagnostics = run_diagnostics(modules)
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")
```

to:

```python
    if settings.is_development:
        diagnostics = run_diagnostics(modules)
        errors = [d for d in diagnostics if d.level == DiagnosticLevel.ERROR]
        if diagnostics:
            print_diagnostics(diagnostics)
        if errors:
            raise SystemExit(f"Module diagnostics: {len(errors)} error(s). Fix before continuing.")
```

Note: The module-level diagnostics stay as-is. The migration diagnostics run inside the lifespan (after the DB is available). Update the lifespan to also run migration diagnostics in dev mode:

After `app.state.migration = await _check_migrations(app.state.db.engine)`, add:

```python
if app.state.settings.is_development:
    from simple_module_db.base import all_module_bases
    from simple_module_core.diagnostics import MigrationDiagnostics, print_diagnostics

    module_tables = {t.name for base in all_module_bases for t in base.metadata.tables.values()}
    mig_diag = MigrationDiagnostics()
    mig_diagnostics = mig_diag.check_table_coverage(
        module_tables=module_tables,
        migrated_tables=module_tables,  # TODO: extract from migration scripts
    )
    if mig_diagnostics:
        print_diagnostics(mig_diagnostics)
```

**Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 5: Commit**

```bash
git add framework/core/src/simple_module_core/diagnostics.py framework/core/src/simple_module_core/__init__.py framework/hosting/src/simple_module_hosting/app_builder.py
git commit -m "feat: integrate migration diagnostics into run_diagnostics and app lifespan"
```

---

### Task 10: Update Makefile targets

**Files:**
- Modify: `Makefile:39-43`

**Step 1: Update the Makefile**

Replace the existing migrate targets (lines 39-43):

```makefile
migrate:
	uv run alembic upgrade head

migrate-create:
	uv run alembic revision --autogenerate -m "$(MSG)"
```

with:

```makefile
# Database migrations
migrate:                    ## Run migrations to head
	cd host && uv run alembic upgrade head

migration:                  ## Create new migration (usage: make migration msg="add foo")
	cd host && uv run alembic revision --autogenerate -m "$(msg)"

downgrade:                  ## Downgrade one revision
	cd host && uv run alembic downgrade -1

migration-history:          ## Show migration history
	cd host && uv run alembic history --verbose
```

Also add `downgrade`, `migration`, and `migration-history` to the `.PHONY` list on line 1.

**Step 2: Verify**

Run: `make migrate` (should succeed if Task 4's migration exists and a test DB is available)

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: update Makefile with cd host for Alembic targets, add downgrade/history"
```

---

### Task 11: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

**Step 2: Run linter**

Run: `uv run ruff check .`
Expected: No errors

**Step 3: Run type checker**

Run: `uv run ty check`
Expected: No new errors

**Step 4: End-to-end migration flow**

Run:
```bash
rm -f host/test_e2e.db
cd host && SM_DATABASE_URL=sqlite:///./test_e2e.db uv run alembic upgrade head
cd host && SM_DATABASE_URL=sqlite:///./test_e2e.db uv run alembic current
cd host && SM_DATABASE_URL=sqlite:///./test_e2e.db uv run alembic downgrade -1
cd host && SM_DATABASE_URL=sqlite:///./test_e2e.db uv run alembic upgrade head
rm -f host/test_e2e.db
```

Expected: Clean upgrade → current shows head → downgrade → re-upgrade → cleanup

**Step 5: Verify no remaining `create_all` references in production code**

Run: `grep -r "create_all\|metadata.create_all" --include="*.py" --exclude-dir=.venv --exclude-dir=__pycache__ .`
Expected: Only in `conftest.py` (test fixtures) — no production code references

**Step 6: Commit any final fixes**
