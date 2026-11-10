# Doctor migration checks (#895) — implementation plan

Design: `docs/superpowers/specs/2026-11-10-doctor-migration-checks-design.md`.

Tasks run in order; 1 and 2 are independent of each other.

1. **`MigrationDiagnostics.check_heads` + `module_table_names`** (core)
   - Files: `framework/core/simple_module_core/diagnostics/_migration.py`,
     `framework/core/tests/test_diagnostics.py`.
   - Test first: at heads → `[]`; no current → SM010 WARNING; one of several
     heads missing → SM010 ERROR naming it; an extra unknown current revision
     with every head present → `[]`.
   - Done: targeted tests pass.

2. **`simple_module_db.migration_state.read_migration_state`** (db)
   - Files: `framework/db/simple_module_db/migration_state.py` (new; also
     takes over `_database_exists` from `data_compatibility.py`),
     `framework/db/tests/test_db_migration_state.py` (new).
   - Test first: no ini → `None`; missing SQLite file → empty current and
     tables, file not created; unstamped file → empty current, its tables;
     stamped file → current revisions.
   - Done: targeted tests pass.

3. **Doctor wiring** (hard: cross-package)
   - Files: `framework/core/simple_module_core/_migration_doctor.py` (new),
     `framework/core/simple_module_core/__main__.py`,
     `framework/core/tests/test_core_migration_doctor.py` (new).
   - Test first, through `main()` with a temp project root holding an
     `alembic.ini` and two revisions: DB at heads with a module table missing
     → SM011, exit 0; DB behind → SM010, exit 1; missing DB → SM010 warning,
     exit 0; unreachable DB → one warning.
   - Done: targeted tests + existing doctor tests pass.

4. **Dev boot SM011**
   - Files: `framework/hosting/simple_module_hosting/_table_coverage.py` (new),
     `framework/hosting/simple_module_hosting/_lifespan.py`,
     `framework/hosting/tests/test_hosting_table_coverage.py` (new).
   - Test first: with a runner set and a table missing, results gain SM011 and
     `rerun()` keeps it; with no runner nothing runs.
   - Done: targeted tests pass.

5. **Docs + CHANGELOG**: `docs/reference/diagnostic-codes.md` (SM010/SM011
   rows, "When diagnostics fire"), `CHANGELOG.md` Fixed.

6. **Full checks**: `make lint`, `make test-py` (PYTEST_WORKERS=8), `make
   ci-doctor`.
