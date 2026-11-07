# Make `alembic check` clean on SQLite (GH #869)

## Goal and scope

On a SQLite database migrated with `upgrade heads`, `alembic check` fails. So does every SQLite
`revision --autogenerate`, which writes the same false operations into the new revision.
Verified on `main` (8f3b9c9b), there are two false diffs:

1. **#869:** `ix_file_storage_stored_file_tenant_browse` is reported as removed and re-added.
   - The model writes `created_at DESC` as `sa.text("created_at DESC")`.
   - SQLite reflects it as the plain column `created_at`, and Alembic compares a column with
     a text element.
2. **Found while reproducing #869:** `users_access_token.expires_at` is reported as a type
   change, `DATETIME` → `TIMESTAMPAware`.
   - Its migration (`b4c1e7d9a025`) created `sa.DateTime(timezone=True)`, and the model
     declares fastapi-users' `TIMESTAMPAware`, whose impl is `TIMESTAMP`.
   - SQLite reflects `DATETIME`, so the type differs. Postgres reflects
     `TIMESTAMP WITH TIME ZONE` for both, which is why CI never saw either diff: its only
     `alembic check` runs on Postgres.

In scope: fix both, protect downstream modules from the first, and make CI run `alembic check`
on SQLite. Out of scope: any schema change (no migration), and the expression-index
limitation Alembic already handles (pure expression indexes are skipped on SQLite).

## Approach

1. **Fix the model in `file_storage`.** Replace `sa.text("created_at DESC")` with
   `sa.desc(sa.column("created_at"))`. (Implementation note: the plain string form
   `sa.desc("created_at")` wraps a text label, which Alembic still treats as an
   expression, so it did not fix the diff.)
   - Both compile to the identical `CREATE INDEX … (tenant_id, is_deleted, created_at DESC, id)`
     on SQLite and Postgres, so no migration is needed.
   - Measured: `desc()` over a column compares clean on SQLite and on Postgres, and the
     `sa.text()` form compares clean only on Postgres.
2. **Guard for other modules in `make_include_object`** (the issue's suggestion).
   - On SQLite only, skip comparing an index pair when one side has a text element of the
     form `<column> [ASC|DESC]` and both sides agree on uniqueness and column names, with
     that element read as its column.
   - Any other difference is still reported: a different column, a real expression such as
     `lower(email)`, or a uniqueness change.
   - The dialect comes from `alembic.context.get_context()`. When no migration context is
     active, the guard does nothing.
   - Scaffolded hosts get the guard without editing `env.py`, because they already call
     `make_include_object`.
3. **Fix the `expires_at` type in `users`.** Declare `sa_type=AwareDateTime()`, the repo
   convention (CLAUDE.md § Database).
   - It renders as `sa.DateTime(timezone=True)`, which matches the migration exactly.
   - Values still read back aware UTC.
   - On write, AwareDateTime converts an aware non-UTC value to UTC, where `TIMESTAMPAware`
     stored its wall time as is. Every writer passes UTC (`now_utc`, the strategy's deadline),
     so stored values do not change.
   - `created_at` stays `TIMESTAMPAware`: the initial migration created it as that type, so it
     already compares clean.
4. **CI guard.** `make ci-doctor` already migrates a throwaway SQLite database. It now also runs
   `alembic check` against that database, so a new SQLite-only false diff fails the PR instead
   of reaching a downstream host.

Rejected:
- **The guard alone** (no model change): it leaves the framework's own model relying on a
  comparison that is skipped.
- **A `compare_type` hook that treats SQLite `TIMESTAMP` and `DATETIME` as equal:** every
  existing host would have to edit its `env.py` to get it, and the model fix needs nothing.
- **A migration that retypes `expires_at`:** Postgres already matches, so it would be a
  no-op there. On SQLite it would be a batch table rebuild of the auth token table for no
  behaviour change.

## Decisions made

- The guard matches only a single identifier with an optional `ASC`/`DESC`, plus optional
  `NULLS FIRST|LAST`, optionally double-quoted. Anything else in a text element is a real
  expression and keeps today's behaviour.
- The guard lives in the private module `simple_module_db._sqlite_index_compare`, called from
  the existing foreign-key filter's `include_object` in `simple_module_db.migrations`.
  `make_include_object` keeps its signature. It reuses core's `unwrap_ordering` helper.
- `docs/module-authoring.md` (Migrations section) gets one sentence: write an ordered index
  column as `sa.desc(sa.column("col"))`, not `sa.text("col DESC")` or `sa.desc("col")`.
- The guard also accepts the `sa.desc("col")` label form, and SM026 counts a column wrapped
  in `desc()`/`asc()` as a column, not as an unverifiable expression.
- CHANGELOG `[Unreleased]` → Fixed, citing #869.
- The `alembic check` step in `ci-doctor` runs from the repo root like `make migrate`, using
  the same `SM_DATABASE_URL`.

## Testing

- **New `framework/db/tests/test_migrations_sqlite_index_compare.py`**, against an in-memory
  SQLite database through a real `EnvironmentContext`, so `get_context()` is exercised:
  - a mixed `text("col DESC")` index compares clean with the filter;
  - the same index without the filter still shows the remove/add pair, which proves the test
    reproduces the bug;
  - a column change, a uniqueness change, and a `lower(email)` text element are all still
    reported;
  - called with no active migration context, the filter neither raises nor skips.
- **Postgres:** a test patches the migration context's dialect to Postgres and confirms the
  guard never skips there (no live Postgres needed).
- **`file_storage`:** the model's index elements are plain columns or `desc()`, with no text
  element.
- **`users`:** an `expires_at` round trip on SQLite reads back aware UTC.
- **Whole branch:** `make ci-doctor` (now including `alembic check`) passes locally, and
  `make migrations-roundtrip-pg` passes against the dev-services Postgres, proving Postgres
  still reports no diff.
- Full `make lint`, `make test-py` and `make test-js`. No browser QA: nothing user-visible
  changes.

## Risks

- **`alembic check` on SQLite may surface other false diffs** in modules that CI does not
  enable. `ci-doctor` migrates every installed module, and the local run found exactly these
  two, so the gate is clean today.
- **A downstream module may rely on `TIMESTAMPAware`'s non-UTC write behaviour for
  `expires_at`.** The column belongs to `users`, and nothing outside it writes the column
  (checked by grep).
