---
trigger: glob
globs: "**/tests/**, **/tests-js/**, **/*.test.ts, **/*.test.tsx"
---

## Tests & fixtures

`simple_module_test` (`framework/testing/`, auto-loaded via `pytest11`) provides
app-level fixtures to every test directory; the root `conftest.py` is thin.
It ignores project dotenv files before collection and defaults to importlib mode.
Test support directories are listed explicitly in pytest's `pythonpath` setting.
`docs/testing/fixtures.md`.

- `settings`: in-memory SQLite, `multi_tenant=True`, `auth_provider="users"`,
  `vite_dev_url="http://localhost:5050"`.
  `SM_TEST_DATABASE_URL=postgresql+asyncpg://…` switches the whole suite to
  Postgres; `make test-py-pg` uses `-p no:anyio` because an asyncpg connection
  cannot cross event loops.
- `db_state`, `engine`, `db_session`: fresh `DatabaseState` per test;
  `db_session` creates all module tables and stamps `alembic_version` at heads.
- `app`: `create_app(settings)` with lifespan, seeds `admin@test`; `client` /
  `authenticated_client` (`httpx.AsyncClient`, the latter with a forged admin
  session); `tenant_client(role)` for tenant-scoped requests;
  `setup_pending_app`, `fake_event_bus`, `build_test_app`, `redis_server`,
  `captured_mail`.
- `inertia_page(resp)` / `InertiaPage.from_response(resp)` parse an HTML or JSON
  Inertia page for prop assertions and partial/deferred reloads.
- Module-specific fixtures live in each module's `modules/<m>/tests/conftest.py`.
- The plugin drops password hashing to the minimum work factor (hashes stay
  real); pass `password_hash=` or set `SM_TEST_REAL_PASSWORD_HASHING=1` to test
  real parameters.
- The suite runs under xdist, so tests must collect identically in every
  worker: no `uuid4()`/random values in `parametrize` ids, and anything shared
  across processes (a Redis channel, a file) needs a per-worker name.
- E2E lives in `tests/e2e/` behind the `e2e` marker against a live server
  (`docs/e2e-testing.md`); it needs `uv run playwright install chromium` once
  and `SM_RATE_LIMIT_PUBLIC=1000/minute` on the server.
