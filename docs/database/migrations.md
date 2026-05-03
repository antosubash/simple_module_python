# Migrations

All migrations live in `migrations/versions/` in your app — **not** in module packages. Alembic runs from the app root (`alembic.ini`) and shares the app's `.env` / `SM_DATABASE_URL`.

## Why centralized?

- **Dependency ordering is global.** If `invoices` depends on `orders.order.id`, their migrations must order correctly. One linear Alembic history enforces this.
- **Autogenerate sees everything.** `migrations/env.py` calls `build_module_metadata()` to union every installed module's `MetaData`. Autogenerate diffs the DB against that union and writes one migration covering all changes.
- **Operators run one command.** `make migrate` is the only target. No "did you also run `orders/migrate`?" footgun.

Each module's *first* migration sets `branch_labels = ("<module_name>",)` so you can still downgrade one module at a time with `alembic downgrade <module>@base`.

## Day-to-day workflow

### Create a migration

```bash
uv run alembic revision --autogenerate -m "add orders tables"
```

The resulting file lands in `migrations/versions/XXXX_add_orders_tables.py`.

**Always open and read the generated file** before committing. Autogenerate is good but not perfect:

- It detects column additions, drops, type changes, index/constraint changes, new tables.
- It **misses** semantic constraints (e.g. "this ENUM now has one more value"), and it sometimes produces drops that should be renames.
- Constraint naming needs to be stable — provide explicit `name="..."` kwargs when creating indexes/constraints in your models.

### Apply migrations

```bash
make migrate
```

Runs `alembic upgrade head`. Idempotent.

### Downgrade

```bash
uv run alembic downgrade -1              # back one revision
uv run alembic downgrade <revision_id>   # to a specific revision
uv run alembic downgrade orders@base     # back to the state before the orders module existed
```

`orders@base` uses the `branch_labels` marker from the module's first migration. Module-level downgrade is the mechanism for uninstalling a module cleanly.

## First migration of a new module

When you scaffold a module with `sm create-module`, the *first* autogenerate revision produces a file that needs this marker added by hand:

```python
# migrations/versions/XXXX_add_orders_tables.py

revision = "..."
down_revision = "..."
branch_labels = ("orders",)     # ← add this
depends_on = None
```

Once the marker is in place, all future `orders` migrations inherit the branch.

## Alembic environment setup

`migrations/env.py` (in your app) looks roughly like:

```python
from simple_module_db.base import build_module_metadata
from simple_module_db.migration_support import make_include_object

target_metadata = build_module_metadata()
include_object = make_include_object()

context.configure(
    target_metadata=target_metadata,
    include_object=include_object,
    compare_type=True,
    compare_server_default=True,
)
```

- `target_metadata` — union of every module's `MetaData`.
- `include_object` — filters out system tables (`alembic_version`) and any host-owned tables you don't want tracked.
- `compare_type=True` — detects type changes (e.g. `VARCHAR(50)` → `VARCHAR(100)`).
- `compare_server_default=True` — detects default-value changes.

## Boot-time migration check

On startup, the framework compares `alembic_version` to the migration head:

- **Development:** prints a warning if the DB is behind. Result stored on `app.state.migration`.
- **Production:** fails boot with `SM010`. Don't ship a web process that's pointed at an unmigrated DB.

Fix locally with `make migrate`. In production, run migrations before rolling over the web tier.

## Diagnostic: `SM011`

Fires as a warning when a module's model declares a table that doesn't appear in any Alembic migration. Typical causes:

- You added a model but haven't generated a migration for it yet.
- You renamed a table but the old migration still references the old name.
- You used `__abstract__ = True` somewhere it shouldn't be.

The dev-mode boot log prints the offending table names. Resolution: run `uv run alembic revision --autogenerate -m "..."`, review, `make migrate`.

## Cross-module foreign keys

If `invoices` has an FK to `orders.order.id`:

- Alembic will emit `ADD CONSTRAINT` in the invoices table's migration.
- The migration that creates `invoices_invoice` must come **after** the one that creates `orders_order` in linear history.
- `sm create-module` + `uv run alembic revision --autogenerate` handle this naturally as long as `depends_on` is correct in `ModuleMeta`.

On Postgres, cross-schema FKs work natively (`orders.order.id ← invoices.invoice.order_id`).

On SQLite, FKs are off by default but the test suite enables them; in production SQLite use (rare), set `PRAGMA foreign_keys = ON`.

## Data migrations

Alembic supports ad-hoc `op.execute("UPDATE ...")` inside a migration. Use for:

- Backfilling new NOT NULL columns — add as nullable, backfill, alter to NOT NULL.
- Renaming columns — `op.alter_column` with `new_column_name=...` preserves data.
- Migrating enum values.

Data migrations run as part of `alembic upgrade`. If they fail mid-way, you're left at an intermediate state — design them to be **idempotent** (use `ON CONFLICT`, `IF EXISTS`, `UPDATE ... WHERE x IS NULL`).

For long-running backfills on big tables, break into batches and run outside Alembic:

```python
# scripts/backfill_orders_total.py
async def backfill(batch_size=1000):
    ...
```

## Migration drift in monorepos

`git pull` introducing two parallel branches of Alembic revisions:

```text
revision A  ← you created
revision B  ← teammate's branch created
```

Both have `down_revision = <previous>`. Alembic will refuse `upgrade head` on a tree with multiple heads. Resolve by:

1. `uv run alembic heads` — list them.
2. `uv run alembic merge -m "merge A and B" <rev-A> <rev-B>` — creates a merge revision with both as parents.
3. Commit the merge revision.

Keep merges small; a merge revision with its own `op.*` logic is a code smell.

## Initial-migration gotchas

When you autogenerate a migration for a freshly-added module, autogenerate writes `op.create_table(...)` for every table in the module's `MetaData`. Inspect:

- Are the schema / table names right for your provider (`orders.order` on Postgres vs `orders_order` on SQLite)?
- Do indexes and constraints have stable names? Rename via `name=...` on the model if not.
- Did autogenerate also pick up any **other** module's tables? That means you forgot `make migrate` after the last scaffold. Squash the file down to just this module's changes.

## Testing migrations

The `db_session` fixture stamps `alembic_version` at head on a fresh in-memory DB, which validates that `build_module_metadata()` + your migrations produce a schema the tables can operate against. That said, integration tests don't run every Alembic op — if you want to exercise the migrations explicitly:

```python
@pytest.mark.asyncio
async def test_migration_up_then_down(tmp_path):
    from alembic.config import Config
    from alembic import command

    db_url = f"sqlite:///{tmp_path}/migrate_test.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
```

That catches the common "autogenerate wrote a broken downgrade" class of bugs.
