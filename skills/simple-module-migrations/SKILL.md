---
name: simple-module-migrations
description: Use when generating, applying, or reviewing Alembic migrations in a simple_module_python host project, especially after installing or upgrading a module package. Triggers on "alembic revision", "autogenerate", "branch labels", "downgrade", "SM010", "SM011", or "migration drift".
---

# simple_module_python: migrations

## The cardinal rule

**Migrations live in the host, never in the module package.** A module ships SQLModel tables only. The host developer generates one migration each time a module is installed or its tables change.

```
my_host/                       # the host project
├── alembic.ini
├── migrations/
│   ├── env.py                 # framework template
│   └── versions/              # ALL revisions live here, regardless of owning module
│       ├── 20240101_initial_users.py        # branch_labels=("users",)
│       ├── 20240115_initial_orders.py       # branch_labels=("orders",)
│       └── 20240210_orders_add_total.py
└── pyproject.toml             # depends on each installed module
```

## How autogenerate sees every module

The host's `migrations/env.py` (scaffolded by `sm create-host`) calls:

```python
from simple_module_db import build_module_metadata, make_include_object

target_metadata = build_module_metadata()      # imports every installed module's <pkg>.models
include_object  = make_include_object(target_metadata)
```

`build_module_metadata()` walks the `simple_module` entry-point group, imports each module's `models` submodule, and returns a unified `MetaData`. `make_include_object(metadata)` allowlists only tables owned by installed modules — any host-owned tables outside the module system are preserved untouched. So one `alembic revision --autogenerate` call covers every installed module in a single pass; editable installs and wheels behave identically.

## Adding a new module

```bash
# 1. Install the module into the host environment
pip install simple_module_orders
# or for a workspace: uv sync

# 2. Generate the migration
uv run alembic revision --autogenerate -m "add orders module"

# 3. Review the generated file (see "Branch labels" below)
# 4. Apply
uv run alembic upgrade head
```

### Branch labels — set on the FIRST revision per module

Each module's first revision must set a `branch_labels` tuple matching the module name, lowercased:

```python
# migrations/versions/20240115_initial_orders.py
revision = "abc123"
down_revision = "previous_head"
branch_labels = ("orders",)        # ← required on this first revision
depends_on = None
```

Why: it lets operators roll back **just one module's** schema:

```bash
alembic downgrade orders@base    # drops everything orders-owned, leaves other modules
```

Without the label, `downgrade <revision>` walks linear history and rolls back unrelated modules' migrations sitting between. The autogenerate template doesn't add the label automatically; you have to edit the file before applying.

Subsequent revisions for the same module **don't** need a `branch_labels` — only the first.

## Updating a module's schema

```bash
# Change models.py in the module (or pip install --upgrade <module>)
uv run alembic revision --autogenerate -m "orders: add total column"
uv run alembic upgrade head
```

No branch label on subsequent revisions. The diff covers every installed module — review the generated file to confirm only the intended module's tables changed.

## Diagnostics

| Code | When |
|---|---|
| **SM010** (error) | DB revision is behind migration head — production fails boot, dev warns |
| **SM011** (warning) | Module declares a table that has no entry in migration history — usually means you added a model and forgot to autogenerate |

Both fire at boot. SM010 in production is fatal: deploy a migration before deploying the code that depends on it.

## Pitfalls

- **Skipped the branch label on the first revision.** `alembic downgrade <module>@base` then fails or silently rolls back unrelated revisions. Fix by editing the migration file before applying; if already deployed, write a no-op revision that adds the label retroactively.
- **Renamed a column.** Autogenerate emits `drop_column` + `add_column`, which loses data. Edit to `op.alter_column(..., new_column_name=...)` and write the matching `downgrade()`.
- **Hand-edited operations with stubbed `downgrade()`.** Server defaults, CHECK constraints, expression indexes — Alembic can't always infer these. When you fill in `upgrade()`, fill in `downgrade()` too.
- **Concurrent `alembic upgrade head` from multiple processes.** The `alembic_version` table isn't race-safe across all backends. Run upgrades from one place (a release pipeline step), not from the booting app.

## Related skills

- **simple-module-database** — defining tables that autogenerate will pick up
- **simple-module-doctor** — interpreting SM010/SM011 and other boot-time codes
