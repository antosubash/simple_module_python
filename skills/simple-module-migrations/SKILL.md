---
name: simple-module-migrations
description: Use when generating, applying, or reviewing Alembic migrations in a simple_module_python host project, especially after installing or upgrading a module package. Triggers on "alembic revision", "autogenerate", "branch labels", "downgrade", "SM010", "SM011", or "migration drift".
---

# simple_module_python: migrations

## The cardinal rule

**Migrations live in the host, never in the module package.** A module ships SQLModel tables only. The host developer generates one migration each time a module is installed or its tables change.

```
host/                          # the host project (in the repo root)
├── alembic.ini                # script_location = %(here)s/migrations
├── migrations/
│   ├── env.py                 # framework template
│   └── versions/              # ALL revisions live here, regardless of owning module
│       ├── 77162e7b184b_initial_schema.py    # bundles the bootstrap modules
│       ├── 70786227af4c_add_audit_log_tables.py   # branch_labels=("audit_log",)
│       └── 168a2882f443_keycloak_initial_schema.py # branch_labels=("keycloak",)
└── pyproject.toml             # depends on each installed module
```

Alembic always runs from the repo root with `-c host/alembic.ini`, so it shares
the app's `.env` / `SM_DATABASE_URL`. `host/migrations/env.py` resolves the URL
from `Settings()` (converting the async driver to a sync one for migrations).

## How autogenerate sees every module

The host's `host/migrations/env.py` (scaffolded by `smpy create-host`) calls:

```python
from simple_module_db import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)

target_metadata = build_module_metadata()      # imports every installed module's <pkg>.models
include_object  = make_include_object(target_metadata)
process_revision_directives = make_process_revision_directives(target_metadata)
# context.configure(..., render_item=render_item)
```

`build_module_metadata()` walks the `simple_module` entry-point group, imports each module's `models` submodule, and merges every module's per-module `MetaData` into one unified `MetaData`. `make_include_object(metadata)` allowlists only tables owned by installed modules — any host-owned tables (and `alembic_version`) outside the module system are preserved untouched. So one autogenerate call covers every installed module in a single pass; editable installs and wheels behave identically.

Two extras matter for correctness: `render_item` collapses SQLModel's `AutoString` to `sa.String` and renders `StrEnum` columns so the generated file imports cleanly, and `make_process_revision_directives` re-emits expression-based (functional) indexes — e.g. `lower(email)` — that autogenerate silently drops under SQLite.

All module tables live in the **host's single shared schema** on both Postgres and SQLite (each module still owns its own `MetaData` purely so autogenerate can attribute a table to its module). There is no schema-per-module; `__tablename__` is prefixed with the module name (`orders_order`) to avoid collisions, and a cross-module FK is an ordinary same-schema reference.

## Adding a new module

```bash
# 1. Add the module to the host environment
#    (scaffold a new one: `make new-module name=orders` / `smpy create-module`,
#     or install a packaged one and `uv sync --all-packages`)

# 2. Generate the migration (runs alembic from the repo root, autogenerate)
make migration msg="add orders module"

# 3. Review the generated file (see "Branch labels" below)
# 4. Apply
make migrate
```

`make migrate` runs `alembic -c host/alembic.ini upgrade heads` — note **`heads`** (plural). Branch labels create multiple independent heads, so `upgrade head` (singular) would error or under-apply.

### Branch labels — set on the FIRST revision per module

Each new module's first revision should set a `branch_labels` tuple matching the module name, lowercased. Autogenerate does **not** add this — you edit the file by hand before applying:

```python
# host/migrations/versions/70786227af4c_add_audit_log_tables.py
revision = "70786227af4c"
down_revision = "41cf2c53660e"
branch_labels = ("audit_log",)     # ← add by hand on this first revision
depends_on = None
```

Why: it lets operators roll back **just one module's** schema, which is how a module is uninstalled cleanly:

```bash
make downgrade   # back one revision; OR, to a target:
uv run --project host alembic -c host/alembic.ini downgrade audit_log@base
```

`audit_log@base` drops everything that module owns and leaves the others. Without the label, downgrading to a bare revision id walks linear history and rolls back unrelated modules' migrations sitting between.

Subsequent revisions for the same module **don't** need a `branch_labels` — only the first; they inherit the branch.

> Exception: the repo's bootstrap `initial_schema` revision bundles several core modules (users, permissions, settings, file_storage, feature_flags, background_tasks) into one unlabeled root migration. The per-module `branch_labels` convention applies to modules added **after** that bootstrap.

## Updating a module's schema

```bash
# Change models.py in the module (or upgrade a packaged module + uv sync)
make migration msg="orders: add total column"
make migrate
```

No branch label on subsequent revisions. The diff covers every installed module — review the generated file to confirm only the intended module's tables changed.

## Diagnostics

| Code | When |
|---|---|
| **SM010** (error) | DB revision is behind migration head |
| **SM011** (warning) | Module declares a table that has no entry in migration history — usually means you added a model and forgot to autogenerate |

SM010/SM011 are **not** emitted at boot or by `make doctor`. They only surface when a caller passes `migration_state=` / `module_tables=` / `migrated_tables=` to `run_diagnostics(...)` — e.g. a CI job asserting migration health. The boot-time guard is separate: `check_migrations()` (in the lifespan) raises a plain `RuntimeError` — not an SM code — in **both dev and prod** if the DB is behind head. Operationally the rule is unchanged: deploy the migration before the code that depends on it.

## Pitfalls

- **Skipped the branch label on the first revision.** `alembic downgrade <module>@base` then fails or silently rolls back unrelated revisions. Fix by editing the migration file before applying; if already deployed, write a no-op revision that adds the label retroactively.
- **Renamed a column.** Autogenerate emits `drop_column` + `add_column`, which loses data. Edit to `op.alter_column(..., new_column_name=...)` and write the matching `downgrade()`.
- **Hand-edited operations with stubbed `downgrade()`.** Server defaults, CHECK constraints, expression indexes — Alembic can't always infer these. When you fill in `upgrade()`, fill in `downgrade()` too.
- **Concurrent `make migrate` (`upgrade heads`) from multiple processes.** The `alembic_version` table isn't race-safe across all backends. Run upgrades from one place (a release pipeline step), not from the booting app.
- **Functional index missing under SQLite.** Expression indexes like `lower(email)` are re-emitted by `make_process_revision_directives`, but if your env.py wiring drops it the index silently vanishes on SQLite — verify the generated file actually contains the `op.create_index(...)` for it.

## Related skills

- **simple-module-database** — defining tables that autogenerate will pick up
- **simple-module-doctor** — interpreting SM010/SM011 and the other diagnostic codes
