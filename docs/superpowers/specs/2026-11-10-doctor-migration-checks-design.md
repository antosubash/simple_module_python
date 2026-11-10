# Doctor runs the migration checks SM010 and SM011 (#895)

## Goal & scope

`smpy doctor` / `make doctor` never report `SM010` (database behind head) or
`SM011` (a module table no migration creates), although `CLAUDE.md` and
`docs/reference/diagnostic-codes.md` promise both. `run_diagnostics()` runs them
only when it is handed a `migration_state`, and neither caller (doctor in
`simple_module_core/__main__.py`, the dev boot in
`simple_module_hosting/_dev_boot.py`) passes one. A new module's table can go
unmigrated with no warning.

In scope: doctor reports both codes; the development boot (and so the in-app
Doctor screen) reports `SM011`; tests; docs; CHANGELOG.
Out of scope: changing what a production boot refuses; `alembic check`-style
column drift (CI already runs `alembic check`, #869).

## Approach

Chosen: **read the state from the database doctor already points at.**
Doctor reads `alembic_version` and the table list from `SM_DATABASE_URL`, and
the heads from the host's `alembic.ini`. When the database is at every head,
any table a selected module's models declare that the database does not have
is a table no migration creates: `SM011`. Behind head is `SM010`.

Rejected:
- *Scan the revision files for `op.create_table(...)`* (what the issue
  sketched). It misses `rename_table`, batch operations, tables built in
  helpers and raw SQL, so it would raise false `SM011`s on this repo's own
  history; the database is the ground truth for "what the migrations create".
- *Migrate a throwaway SQLite database inside doctor.* Accurate, but slow on
  every run, and `make ci-doctor` already does exactly this before calling
  doctor, so the database approach gets the same answer in CI for free.

## Design

**`simple_module_db.migration_state`** (new; db owns Alembic, core may not
import hosting):
`async def read_migration_state(database_url, alembic_ini) -> MigrationState | None`
returns `heads`, `current` (plural `get_current_heads()`, like
`migration_status`) and `tables` (`inspect(...).get_table_names()`), or `None`
when there is no `alembic.ini` / no revisions. It never creates a database: a
SQLite file URL whose file does not exist yields an empty state instead of
connecting (connecting would create `app.db`).

**`MigrationDiagnostics.check_heads(current, heads)`** (core, new beside the
existing `check_revision_mismatch`, which stays for `run_diagnostics`
callers): the same rule the boot uses (`heads - current`):
- at every head → nothing;
- never migrated (no `alembic_version` rows) → `SM010` **WARNING**, "run
  `make migrate`" (a production boot sends this database to `/setup` rather
  than refusing it, so it is not an error);
- behind on some branch → `SM010` **ERROR** naming the missing heads (a
  production boot refuses this).
`check_table_coverage` (existing) gives `SM011`, run only when at every head.

**Doctor** (`simple_module_core/__main__.py` → a `_migration_doctor.py` helper
like `_data_doctor.py`): skips silently when `simple_module_db` is not
installed; resolves `alembic.ini` as the CLI does (project root `alembic.ini`,
else `host/alembic.ini`); module tables come from `module_all_tables()` over the
selected modules (the set SM026 already uses). A database it cannot reach (a
stopped Postgres) gives one `SM010` WARNING saying the checks were skipped,
not a crash.

**Dev boot**: the diagnostics runner runs at build time, before the database
is open, so `SM011` is computed in the lifespan instead: in development, once
`migration_status` reports the database at head, the lifespan reads the
table list from the app's own engine, prints any `SM011`, and wraps
`diagnostics_state.runner` so the in-app Doctor screen (which already maps
`SM010`/`SM011` to its migrations check) shows them on every re-run. `SM010` at
boot is already enforced by the lifespan's own refusal.

## Decisions made

- Never-migrated is a WARNING, behind is an ERROR (mirrors production boot).
- Unreachable database: WARNING, migration checks skipped; doctor still exits
  on the other findings.
- `SM011` only when at every head; behind head the missing table may simply be
  in a pending revision.
- Module tables = tables in each selected module's `models` (as SM026). Tables
  declared outside `models` are not checked (missed, never falsely reported).
- No new setting, no new code; docs: `docs/reference/diagnostic-codes.md`
  (when each fires, that doctor reads `SM_DATABASE_URL`), CHANGELOG Fixed.

## Testing

- `check_heads`: at heads, never migrated, behind (multi-head), extra unknown
  revision is not "behind".
- `read_migration_state`: a SQLite file stamped at heads (the test plugin's
  create-all + stamp), an unstamped one, a missing file is not created.
- Doctor `main()` end to end: a database at heads with one module table
  dropped reports `SM011` and exits 0 (warning); a database stamped one
  revision behind reports `SM010` and exits 1; a missing DB file warns.
- Dev boot: the lifespan helper adds `SM011` to `diagnostics_state` and
  `rerun()` keeps it.
No browser QA (`--skip-browser`): CLI and boot diagnostics only.

## Risks

- `make doctor` on a developer checkout whose dev database is behind will now
  exit 1. That is the point of SM010, and the message says `make migrate`.
- `make ci-doctor` migrates first, so CI should stay green; if this repo's own
  modules have a table no migration creates, doctor will now say so and the
  fix is a migration (that would be a real bug the check exists to find).
