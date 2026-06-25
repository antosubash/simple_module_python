---
name: simple-module-testing
description: Use when writing or running pytest tests in a simple_module_python project — picking the right fixture, understanding why a test session sees pre-stamped alembic revisions, getting an `authenticated_client`, or running a single test / e2e suite. Triggers on "how do I test", "fixture", "authenticated_client", "asyncio_mode", "make test", "make test-e2e", "playwright", or any new file under `tests/` or `<module>/tests/`.
---

# simple_module_python: testing

## What's already wired up

Root `conftest.py` provides app-level fixtures that **every** test directory inherits — module tests don't redeclare them. `pyproject.toml` sets `asyncio_mode = "auto"` and `addopts = "-m 'not e2e and not perf' --durations=20 --benchmark-disable"`, so:

- `async def test_*` works without `@pytest.mark.asyncio`.
- `make test` excludes the `e2e` and `perf` markers by default; only `make test-e2e` runs e2e, and only `make bench` runs the `perf` benchmarks (`tests/benchmarks`).
- Every run prints `--durations=20` (the 20 slowest tests) so a slow function-scoped fixture surfaces without an opt-in flag.

| Fixture | What you get |
|---|---|
| `settings` | `Settings` configured for in-memory SQLite (`sqlite+aiosqlite:///:memory:`), `multi_tenant=True`, `tenant_header="X-Tenant-ID"`. |
| `db_state` / `engine` | Fresh `DatabaseState` per test with the framework's SQLAlchemy listeners (`AuditMixin`, soft-delete filter, tenant scoping) registered. |
| `db_session` | `AsyncSession` against in-memory SQLite with **all** module tables created and `alembic_version` stamped at head. The stamp matters: without it the boot-time `check_migrations` raises SM010 and the `app` fixture can't start. |
| `app` | A live FastAPI app — `create_app(settings)` plus lifespan started/stopped. Tables are pre-created the same way as `db_session`. |
| `client` | Unauthenticated `httpx.AsyncClient` against `app` via `ASGITransport`. |
| `authenticated_client` | Same client with a forged session cookie carrying a seeded admin (`admin@test` / `test-password`). The seed runs `users.bootstrap.create_admin`, so the users tables must be in scope. |

## Standard test patterns

```python
# Unit test — no app, no HTTP
async def test_service_creates_order(db_session):
    order = await OrdersService(db_session).create(name="x")
    assert order.id is not None

# API test — JSON endpoint
async def test_api_lists_orders(authenticated_client):
    resp = await authenticated_client.get("/api/orders")
    assert resp.status_code == 200

# View test — Inertia endpoint (X-Inertia header)
async def test_view_renders_index(authenticated_client):
    resp = await authenticated_client.get("/orders/", headers={"X-Inertia": "true"})
    assert resp.status_code == 200
    assert resp.json()["component"] == "Orders/Index"
```

`authenticated_client` already carries the cookie — don't manually pass `cookies=`.

## Single-test / focused runs

```bash
# One file
uv run pytest modules/orders/tests/test_service.py

# One test
uv run pytest modules/orders/tests/test_service.py::test_creates_order

# One JS test (vitest's `include` covers packages/** and host/client_app/** only)
npx vitest run packages/ui/src/components/StatCard.test.tsx
```

`make test` runs `test-py` then `test-js`. `make test-py` (`uv run pytest`) and `make test-js` (`npm test` → `vitest run --passWithNoTests`) run only one suite each. Vitest's `include` globs (`vitest.config.ts`) only match `packages/**` and `host/client_app/**`, so a `.test.tsx` placed under `modules/**` is **not** picked up by `make test-js` — colocate UI tests with the page in `host/client_app/` or in a `packages/*` workspace.

## E2E tests (Playwright)

E2E tests live in `tests/e2e/` behind the `e2e` marker. They drive a real Chromium browser against a running stack:

```bash
make dev                              # in one terminal: docker up + API + Vite
uv run playwright install chromium    # one-time, per machine
make test-e2e                         # in another terminal
```

Env vars they read (defaults in parens): `E2E_BASE_URL` (`http://localhost:8000`), `E2E_USERNAME` (`admin@example.com`), `E2E_PASSWORD` (`admin`), `E2E_USER_ID` (optional — enables the password-reset test).

Token-minting helpers in `tests/e2e/conftest.py` use the same `SM_USERS_VERIFICATION_TOKEN_SECRET` as the server, so you don't need to scrape `ConsoleMailer` stdout to grab a verify link.

## Module-test layout

Each module ships its own `tests/` next to its package:

```
modules/orders/
├── orders/                  # package
└── tests/
    ├── __init__.py
    └── test_orders.py       # imports orders.service — name from the scaffold
```

The directory must be listed in the root `pyproject.toml` under `[tool.pytest.ini_options].testpaths` for `make test` to pick it up. Both `smpy create-module` and `make new-module name=<name>` add this entry (via `scripts/new_module.py`'s `update_root_pyproject`); if you scaffolded a module by hand, add it.

## Pitfalls

- **Forgot to use the `db_session` / `app` fixture and called your service with a hand-rolled engine.** The `AuditMixin` / soft-delete / tenant listeners aren't registered on a bare engine — your test passes locally and breaks on the next person's clone. Always go through the fixtures.
- **Reused the same `db_session` across tests via `module`/`session` scope.** The fixture is function-scoped on purpose: in-memory SQLite is per-connection, and shared state across tests masks ordering bugs. Don't widen the scope.
- **Asserted on `auth.user` in a test that uses `client` (not `authenticated_client`).** Without the seeded admin and signed cookie, `auth.user` is `None`. Use `authenticated_client`.
- **Marked an async test with `@pytest.mark.asyncio`.** Redundant under `asyncio_mode = "auto"`; remove it.
- **Ran `make test` to validate an e2e change.** The default suite excludes the `e2e` marker. Use `make test-e2e` (with `make dev` running) for those.
- **CI green but `make test-e2e` fails locally.** E2E isn't part of `make test` or PR CI by default — verify Playwright tests against a live `make dev` before relying on them.

## Related skills

- **simple-module-database** — what `db_session` actually wires up (mixins, listeners)
- **simple-module-doctor** — why `db_session` stamps `alembic_version` (avoids SM010 at app startup)
- **simple-module-creating** — module scaffolding adds the `tests/` entry to `testpaths`
