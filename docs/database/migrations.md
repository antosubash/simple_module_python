# Migrations

All migrations live in `host/migrations/versions/` — **not** in module packages. Alembic runs from the repo root via `host/alembic.ini` and shares the app's `.env` / `SM_DATABASE_URL`.

## Why centralized?

- **Dependency ordering is global.** If `invoices` depends on `orders_order.id`, their migrations must order correctly. One shared Alembic history, with `down_revision` links between modules, enforces this.
- **Autogenerate sees everything.** `host/migrations/env.py` calls `build_module_metadata()` to union every installed module's `MetaData`. Autogenerate diffs the DB against that union and writes one migration covering all changes.
- **Operators run one command.** `make migrate` is the only target. No "did you also run `orders/migrate`?" footgun.

## The real graph

The history is **not** a single linear chain. It has several roots and several heads, and `make migrate` runs `upgrade heads` for that reason. On `main` today:

| Root | Branch |
|---|---|
| `77162e7b184b` initial schema | the users trunk (also holds file_storage, background_tasks, api_tokens revisions) |
| `e36ab09c4a92` tenants initial schema | tenants (`f1a9c3d7b2e4` head) |
| `f733c7938fd1` sharing resource share | sharing (root and head) |
| `d263ea727663` framework `sm_lease` table | leases (its own head; [leases](../framework/leases.md)) |

| Head | Owning module | Label Alembic reports |
|---|---|---|
| `f5b1c3e8a207` | file_storage (`size_bytes` BIGINT) | `api_tokens`, `background_tasks`, `file_storage`, `users` |
| `a7c2e91d4b58` | audit_log | `audit_log` |
| `f1a9c3d7b2e4` | tenants | `tenants` |
| `d263ea727663` | framework (`sm_lease`) | `leases` |
| `f6a3b9d2e8c4` | keycloak | `keycloak` |
| `f733c7938fd1` | sharing | `sharing` |

`audit_log` forks off the trunk at `41cf2c53660e`, and `keycloak` forks off the users revision `873ca2015033`.

A module's first migration sets `branch_labels = ("<module_name>",)`. Alembic **inherits** a label onto every descendant, so the label names a revision and everything above it, and it does not isolate the module. It is only a named target (`upgrade <label>@head`, `revision --head <label>@head`) and the source of the Doctor's `module` column, which reads the first label on each revision.

### Known mislabels

The declared `branch_labels` are `audit_log`, `api_tokens`, `background_tasks`, `keycloak`, `tenants`, `sharing`, `leases`, `users` (added by `a625f0b7c912`) and `file_storage` (added by `f5b1c3e8a207`). The graph carries these defects; they are documented rather than rewritten, because changing labels on revisions that installed databases already applied is not worth the risk:

- `51b2058d8afd_api_tokens_initial` sits in the middle of the trunk, so every revision above it (file_storage, background_tasks including the outbox, and the users revisions through `c8e4f1a2b6d9`) reports the `api_tokens` label. The `api_tokens` head is therefore really a users revision.
- `keycloak` branches off a users revision, so a Keycloak-only install still builds the users schema.
- `users`, `file_storage`, `background_tasks`, `settings`, `permissions` and `feature_flags` have no label of their own.

Guidance: give an unlabelled module a `branch_labels` on its **next** revision. Adding a label to an existing revision file is technically possible, because `alembic_version` stores revision ids and never labels, but it also relabels every descendant and changes what `<label>@head` resolves to, so treat it as a deliberate, reviewed change rather than a cleanup.

`host/tests/test_migration_graph.py` pins the roots, heads, each revision's owning module and the mislabels above. Adding a root, head or revision fails it until the table is updated.

## Users token storage upgrade (#626)

Migration `a626b1c8d023` follows `a625f0b7c912` on `users@head` and changes
refresh and access token keys to SHA-256 digests. **Behaviour change:** upgrade
deletes existing refresh/access token rows, requiring one re-login for clients
using them (including `sm_auth` cookies). Other session cookies are unaffected.
Downgrade also deletes token rows: hashes cannot be restored to bearer secrets.
Cookie login, token login and refresh prune up to 100 spent rows per table for
that user. Refresh reuse evidence is retained while the family has a live token, including when
an ancestor has expired; inactive users' rows wait until their next login.

## Day-to-day workflow

### Create a migration

```bash
make migration msg="add orders tables"
```

This runs `alembic -c host/alembic.ini revision --autogenerate` from the repo root. The resulting file lands in `host/migrations/versions/XXXX_add_orders_tables.py`.

**Always open and read the generated file** before committing. Autogenerate is good but not perfect:

- It detects column additions, drops, type changes, index/constraint changes, new tables.
- It **misses** semantic constraints (e.g. "this ENUM now has one more value"), and it sometimes produces drops that should be renames.
- Constraint naming needs to be stable — provide explicit `name="..."` kwargs when creating indexes/constraints in your models.

### Apply migrations

```bash
make migrate
```

Runs `alembic -c host/alembic.ini upgrade heads`. Idempotent.

### Downgrade

```bash
make downgrade                                                 # back one revision
uv run --project host alembic -c host/alembic.ini downgrade <revision_id>   # to a specific revision
```

Do **not** use `downgrade orders@base` to roll back just the orders module. The label names a revision, and `orders@base` unwinds that revision, all of its descendants, and everything beneath it down to the root it sits on, including other modules'. With this graph, `downgrade api_tokens@base` would drop the whole users trunk (users, file_storage, the background_tasks outbox and the initial schema), not only the api_tokens tables.

### Removing one module's schema

- If the module's revisions are the latest on their branch (nothing from another module sits above them), downgrade to the `down_revision` of the module's *first* revision: `alembic -c host/alembic.ini downgrade <that down_revision id>`.
- Otherwise write a dedicated migration that drops the module's tables (and anything depending on them). Other modules are untouched.

## First migration of a new module

When you scaffold a module with `smpy create-module`, the *first* autogenerate revision produces a file that needs this marker added by hand:

```python
# host/migrations/versions/XXXX_add_orders_tables.py

revision = "..."
down_revision = "..."
branch_labels = ("orders",)  # ← add this
depends_on = None
```

The marker names the revision so you can target it (for example `alembic upgrade orders@head`); later `orders` revisions do not need it. It does not turn the module into an independent branch, and it is inherited by every revision stacked on top of it, so put it on the module's own first revision and not on a revision that other modules build on.

## Alembic environment setup

`host/migrations/env.py` looks roughly like:

```python
from simple_module_db import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)

target_metadata = build_module_metadata()
include_object = make_include_object(target_metadata)
process_revision_directives = make_process_revision_directives(target_metadata)

context.configure(
    target_metadata=target_metadata,
    include_object=include_object,
    render_item=render_item,
    process_revision_directives=process_revision_directives,
)
```

- `target_metadata` — union of every module's `MetaData`.
- `include_object` — accepts only tables present in `target_metadata`, so autogenerate never diffs system tables (`alembic_version`) or any host-owned tables outside the module system.
- `render_item` — collapses SQLModel's `AutoString` to `sa.String` and renders `StrEnum` columns with `values_callable` so generated migrations are importable.
- `process_revision_directives` — re-emits expression-based (functional) indexes that autogenerate silently drops under SQLite.

## Boot-time migration check

On startup, the framework compares `alembic_version` to **every** head (`resolve_head_revisions` in `simple_module_hosting.migrations`; the history has several, so it never asks for a single head):

- **Development:** prints a warning if the DB is behind. Result stored on `app.state.migration`.
- **Production:** fails boot with `SM010`. Don't ship a web process that's pointed at an unmigrated DB.

Fix locally with `make migrate`. In production, run migrations before rolling over the web tier.

## Diagnostic: `SM011`

Fires as a warning when a module's model declares a table that doesn't appear in any Alembic migration. Typical causes:

- You added a model but haven't generated a migration for it yet.
- You renamed a table but the old migration still references the old name.
- You used `__abstract__ = True` somewhere it shouldn't be.

The dev-mode boot log prints the offending table names. Resolution: run `make migration msg="..."`, review, `make migrate`.

## Cross-module foreign keys

If `invoices` has an FK to `orders_order.id`:

- Alembic will emit `ADD CONSTRAINT` in the invoices table's migration.
- The migration that creates `invoices_invoice` must come **after** the one that creates `orders_order` in the history (an ancestor, not a sibling branch).
- `smpy create-module` + `make migration` handle this naturally as long as `depends_on` is correct in `ModuleMeta`.

All tables share the host's single schema on both Postgres and SQLite, so a cross-module FK is just an ordinary same-schema reference (`orders_order.id ← invoices_invoice.order_id`).

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
async def backfill(batch_size=1000): ...
```

## Migration drift in monorepos

`git pull` introducing two parallel branches of Alembic revisions:

```text
revision A  ← you created
revision B  ← teammate's branch created
```

Both have `down_revision = <previous>`, so the same branch now has two heads. (Heads on *different* labelled branches are expected and need no merge; `upgrade heads` applies them all.) Resolve a same-branch fork by:

1. `uv run alembic heads` — list them.
2. `uv run alembic merge -m "merge A and B" <rev-A> <rev-B>` — creates a merge revision with both as parents.
3. Commit the merge revision.

Keep merges small; a merge revision with its own `op.*` logic is a code smell.

## Initial-migration gotchas

When you autogenerate a migration for a freshly-added module, autogenerate writes `op.create_table(...)` for every table in the module's `MetaData`. Inspect:

- Are the table names right (the module-prefixed `orders_order`, identical on Postgres and SQLite)?
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
    cfg = Config("host/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "heads")
    command.downgrade(cfg, "base")
```

That catches the common "autogenerate wrote a broken downgrade" class of bugs.
