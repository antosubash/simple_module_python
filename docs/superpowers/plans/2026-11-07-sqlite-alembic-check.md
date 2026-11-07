# Plan: make `alembic check` clean on SQLite (GH #869)

Design: `docs/superpowers/specs/2026-11-07-sqlite-alembic-check-design.md`.

## Task 1: SQLite text-ordered index guard (independent, marked hard)

Files:
- `framework/db/simple_module_db/migrations.py`
- new `framework/db/tests/test_migrations_sqlite_index_compare.py`

1. Write the tests first, against in-memory SQLite through a real `EnvironmentContext` and `compare_metadata`:
   - a mixed `text("col DESC")` index produces no diff with the filter;
   - the same index without the filter still shows the remove/add pair;
   - a changed column, a uniqueness change and a `lower(email)` element are each still reported;
   - with no active migration context, the filter neither raises nor skips.
2. Add a Postgres test, marked `@pytest.mark.postgres` and skipped without `SM_TEST_PG_URL`, showing the guard never skips there.
3. Implement a private helper plus a branch in `include_object`, keeping `make_include_object`'s signature unchanged.

Done: the tests pass, and they fail without the guard. `migrations.py` stays under 300 lines.

## Task 2: models, docs and the CI gate (independent of Task 1)

Files:
- `modules/file_storage/file_storage/models.py`
- `modules/users/users/models/access_token.py`
- a new test in each module's tests
- `Makefile` (`ci-doctor`)
- `docs/module-authoring.md`
- `CHANGELOG.md`

Steps:
1. Write tests:
   - `file_storage`: no `TextClause` among the browse index's elements;
   - `users`: an `expires_at` written and read on SQLite comes back aware UTC.
2. Change `sa.text("created_at DESC")` to `sa.desc(sa.column("created_at"))`, and `expires_at` to `sa_type=AwareDateTime()`. Keep the `TIMESTAMPAware` import, because `created_at` still uses it.
3. In `ci-doctor`, run `alembic check` against the same throwaway database after `make migrate`.
4. Add one docs sentence and a CHANGELOG Fixed entry citing #869.

Done: `make ci-doctor` passes locally, which means the `alembic check` on SQLite is clean.

## Task 3: integrate and verify (after Tasks 1 and 2)

Merge the Task 1 diff, then run `make lint`, `make test-py` (with `SM_TEST_REDIS_URL`), `make test-js`, `make ci-doctor` and `make migrations-roundtrip-pg` (dev-services Postgres).
