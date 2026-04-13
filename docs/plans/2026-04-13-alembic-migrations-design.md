# Alembic Database Migrations — Design Document

**Goal:** Replace the `create_all` approach in module `on_startup` hooks with Alembic-managed schema versioning, adding migration diagnostics to the existing framework.

**Tech Stack:** Python 3.12, SQLAlchemy async, Alembic, FastAPI, UV workspace

---

## Section 1: File Layout

```
host/
├── alembic.ini            # Alembic config — reads SM_DATABASE_URL from env
├── migrations/
│   ├── env.py             # Entry-point discovery to collect all module metadata
│   ├── script.py.mako     # Migration template
│   └── versions/          # Generated migration files
└── main.py                # Existing entry point (unchanged)
```

- `alembic.ini` lives in `host/` alongside the app entry point.
- The `sqlalchemy.url` field in `alembic.ini` is left empty — `env.py` overrides it at runtime from `Settings.database_url`.
- The `versions/` directory is committed to git so migration history is shared.

## Section 2: Discovery & Metadata Collection

`env.py` reuses the framework's entry-point discovery to find all module models automatically:

1. Call `discover_modules()` — this loads entry points, which import module packages, which call `create_module_base()` and define models.
2. After discovery, `all_module_bases` (from `simple_module_db.base`) contains every module's `DeclarativeBase`.
3. Combine all module metadata into a single `MetaData` object for Alembic's autogenerate.
4. Read `Settings.database_url` and convert async drivers to sync equivalents (`+aiosqlite` → removed, `+asyncpg` → `+psycopg2` or removed).

```python
from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases

# Trigger model registration
discover_modules()

# Combine metadata
from sqlalchemy import MetaData
target_metadata = MetaData()
for base in all_module_bases:
    for table in base.metadata.tables.values():
        table.tometadata(target_metadata)
```

New modules with models are automatically picked up — no manual wiring.

## Section 3: Startup Migration Check

Replace `ProductsModule.on_startup`'s `create_all` with a framework-level check in the app lifespan (inside `app_builder.py`):

- Runs **before** any module `on_startup` hooks.
- Reads the current Alembic revision from the database.
- Compares against the head revision from the migration scripts.
- **Raises `RuntimeError`** if the database is not at head — the app refuses to start.
- The error message includes the pending revision count and the fix command.

```python
async def _check_migrations(engine):
    alembic_cfg = Config("host/alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head = script.get_current_head()

    async with engine.connect() as conn:
        def get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()
        current = await conn.run_sync(get_current)

    if current != head:
        pending = list(script.iterate_revisions(head, current))
        raise RuntimeError(
            f"Database is {len(pending)} revision(s) behind "
            f"(at {current!r}, head is {head!r}). Run: make migrate"
        )
```

`ProductsModule.on_startup` removes its `create_all` call entirely.

## Section 4: Makefile Targets & CLI

Update existing Makefile targets to use `cd host` since `alembic.ini` lives there:

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

Standalone CLI also works: `cd host && alembic upgrade head`.

## Section 5: Autogenerate Filtering

Alembic's autogenerate reflects all tables in the database and compares against model metadata. Tables not owned by any module (e.g., Keycloak tables, external schemas) would trigger spurious `DROP TABLE` operations.

**Solution:** Allowlist approach via `include_object` in `env.py`.

```python
MODULE_TABLES = {
    t.name
    for base in all_module_bases
    for t in base.metadata.tables.values()
}

def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in MODULE_TABLES
    if hasattr(object, "table"):
        return object.table.name in MODULE_TABLES
    return True
```

Only tables declared via `create_module_base()` are managed. Everything else in the database is invisible to autogenerate.

## Section 6: Diagnostics

Four diagnostic additions:

### 6a. Pending Migration Count

The startup `RuntimeError` (Section 3) includes the exact count of pending revisions and both the current and head revision identifiers.

### 6b. Health Endpoint — Migration Status

Extend the existing `/health` endpoint to include migration state:

```json
{
  "status": "healthy",
  "migration": {
    "current_revision": "abc123",
    "head_revision": "def456",
    "is_current": false,
    "pending_count": 3
  }
}
```

Store migration state on `app.state` during the lifespan startup check so the health endpoint can read it without re-querying.

### 6c. Module Coverage Check

At startup (dev mode only), compare tables declared in `all_module_bases` against tables present in the latest migration revision. If a module has models with tables that don't appear in any migration, emit a warning:

```
⚠ SM010 [WARNING] Products: Table 'products_orders' declared in models
  but not found in migration history
  ↳ Suggestion: Run make migration msg="add orders table"
```

### 6d. Diagnostic Integration

Add migration checks to the existing `run_diagnostics()` system in `simple_module_core/diagnostics.py`:

- New diagnostic code `SM009`: Migration revision mismatch (ERROR level).
- New diagnostic code `SM010`: Module tables missing from migrations (WARNING level).
- These appear alongside existing module diagnostics in dev mode startup output.

The diagnostics require the database engine, so `run_diagnostics()` gains an optional `db_state` parameter. When `None` (e.g., in unit tests), migration diagnostics are skipped.

---

## Summary of Changes

| Area | Files Modified | Files Created |
|------|---------------|---------------|
| Alembic setup | — | `host/alembic.ini`, `host/migrations/env.py`, `host/migrations/script.py.mako` |
| App builder | `framework/hosting/src/simple_module_hosting/app_builder.py` | — |
| Products module | `modules/products/src/sm_products/module.py` | — |
| Health endpoint | `framework/hosting/src/simple_module_hosting/health.py` | — |
| Diagnostics | `framework/core/src/simple_module_core/diagnostics.py` | — |
| Makefile | `Makefile` | — |
| Dependencies | `framework/db/pyproject.toml` or root `pyproject.toml` | — |
