# DX Hardening — Implementation Plan

> **For Claude:** Execute tasks in order. Each task is independently committable. Stop and surface any surprise (failing test, unexpected file) rather than patching around it.

**Goal:** Implement the design decisions in `docs/plans/2026-04-14-dx-hardening-design.md` to close the deferred review items.

**Design doc:** `docs/plans/2026-04-14-dx-hardening-design.md`

**Branch:** work off `claude/review-framework-dx-FtWsy` (or rebase onto `main` if merged by the time you start).

---

## Task order rationale

Order is roughly "safest, smallest" first so the branch stays green after each commit:

1. Nits (self-contained, no behaviour change for callers).
2. Runtime safety guards (opt-in strictness, no default change for dev users).
3. Routing fix (isolated to dashboard + host).
4. Multi-tenancy opt-in (behaviour change gated by a setting default).
5. `get_db` skip-commit-when-clean (behaviour change observable under profiling).
6. Docs.

---

## Task 1: Investigate and resolve `modules/products/products/validation.ts`

**Files:** `modules/products/products/validation.ts` (inspect); possibly delete or move.

**Steps:**

1. `grep -R "products/validation" modules host packages framework` to check if anyone imports it.
2. If unreferenced: delete and commit.
3. If referenced: move to `modules/products/products/pages/validation.ts` (co-locate with consumers) and fix imports.

**Verify:** `npx tsc --noEmit -p host/client_app/tsconfig.json` clean; `npx biome ci .` clean; `uv run pytest` still 231 passing.

**Commit:** `chore: resolve stray modules/products validation.ts`

---

## Task 2: `print_diagnostics` → stderr

**Files:** `framework/core/simple_module_core/diagnostics.py`

**Steps:**

1. Import `sys` (top of file, alphabetised with the existing stdlib imports).
2. In `print_diagnostics`, replace `print(str(d))` and the summary `print(...)` at lines ~390-394 with `print(..., file=sys.stderr)`.
3. Add a unit test in `framework/core/tests/test_core.py` that calls `print_diagnostics([some_error])` with `capsys` and asserts the output is on stderr.

**Verify:** `uv run pytest framework/core/tests/test_core.py -k diagnostics`

**Commit:** `fix(diagnostics): write print_diagnostics output to stderr`

---

## Task 3: Dedupe `all_module_bases`

**Files:** `framework/db/simple_module_db/base.py`, `framework/db/tests/test_db.py`

**Steps:**

1. In `base.py`, replace the module-level `all_module_bases: list[...]` with `_bases_by_key: dict[str, type[DeclarativeBase]] = {}`. On creation, do `_bases_by_key[cache_key] = ModuleBase`.
2. Expose a module-level `all_module_bases` via `__getattr__` on the module (PEP 562) that returns `list(_bases_by_key.values())`. This preserves the `from simple_module_db.base import all_module_bases` import path used by `host/migrations/env.py` and `conftest.py`.
3. Add a test that calls `create_module_base("x", SQLITE)` twice and asserts `len(all_module_bases)` does not grow past 1.

**Verify:** `uv run pytest framework/db/tests/`

**Commit:** `refactor(db): dedupe all_module_bases via keyed dict`

---

## Task 4: Make `_PROJECT_ROOT` explicit

**Files:** `framework/hosting/simple_module_hosting/app_builder.py`, `host/main.py`

**Steps:**

1. In `app_builder.py`, replace:
   ```python
   _PROJECT_ROOT = Path(__file__).resolve().parents[3]
   ```
   with:
   ```python
   _PROJECT_ROOT = Path(os.environ.get("SM_PROJECT_ROOT") or Path(__file__).resolve().parents[3])
   ```
   Add `import os` if missing.
2. In `host/main.py`, before `create_app(...)`:
   ```python
   import os
   from pathlib import Path

   os.environ.setdefault("SM_PROJECT_ROOT", str(Path(__file__).resolve().parent.parent))
   ```
3. Add a test that sets `SM_PROJECT_ROOT` to a tmp_path and asserts `app_builder` resolves static / templates under it (use `monkeypatch.setenv` + import reload or, cleaner, refactor the fallback into a helper and test the helper directly).

**Verify:** `uv run pytest framework/hosting/tests/`; manual smoke `make dev` still serves `/static/*`.

**Commit:** `refactor(hosting): honour SM_PROJECT_ROOT env var for project root lookup`

---

## Task 5: Enforce `ModuleMeta` at discovery time

**Files:** `framework/core/simple_module_core/discovery.py`, `framework/core/simple_module_core/exceptions.py`, `framework/core/tests/test_core.py`

**Steps:**

1. In `exceptions.py`, extend `ModuleError` (no new class needed) — or add `InvalidModuleError(ModuleError)` if a tighter type helps callers.
2. In `discovery.py` `discover_modules()`, after `instance = module_cls()`:
   ```python
   meta = getattr(instance, "meta", None)
   if not isinstance(meta, ModuleMeta):
       msg = (
           f"Module {module_cls.__qualname__!r} loaded from entry point "
           f"{ep.name!r} is missing 'meta = ModuleMeta(...)'"
       )
       if strict:
           raise ModuleError(msg)
       logger.error(msg)
       continue
   ```
3. Update the `isinstance(instance, ModuleBase)` branch to also honour `strict`.
4. Add tests: one module class with no `meta`, one with `meta = None`, one with a plain string — each should raise under `strict=True` and log+skip under `strict=False`.

**Verify:** `uv run pytest framework/core/tests/`

**Commit:** `feat(core): fail fast on modules missing valid ModuleMeta`

---

## Task 6: `discover_modules(strict=...)` and wire it up

**Files:** `framework/core/simple_module_core/discovery.py`, `framework/hosting/simple_module_hosting/app_builder.py`

**Steps:**

1. Give `discover_modules` a `strict: bool = False` kwarg (continues Task 5). Under `strict=True`, re-raise any `ep.load()` exception as `ModuleError(f"Failed to load entry point {ep.name!r}: {exc}")`.
2. In `app_builder.create_app`, call `discover_modules(strict=not settings.is_development)`.
3. Verify `host/migrations/env.py` and `conftest.py` still call `discover_modules()` (no kwarg) — the default remains `strict=False`, which is what they need.
4. Add a test that patches entry-point loading to raise, then asserts: strict=False logs + returns partial list; strict=True re-raises.

**Verify:** `uv run pytest framework/core/tests/`

**Commit:** `feat(discovery): add strict mode so production boot fails loudly on bad modules`

---

## Task 7: Dashboard routing

**Files:**
- `modules/dashboard/dashboard/module.py` (change `view_prefix`)
- `modules/dashboard/dashboard/endpoints/views.py` (remove landing route if present)
- `modules/dashboard/dashboard/pages/Landing.tsx` (move → `host/client_app/pages/Landing.tsx`)
- `host/client_app/app.tsx` / `host/client_app/pages/` (ensure Landing renders)
- `host/main.py` or new `host/routes.py` (register the landing route)

**Steps:**

1. Change `DashboardModule.meta.view_prefix` from `""` to `"/dashboard"`.
2. Inspect `modules/dashboard/dashboard/endpoints/views.py`. For any route currently at `/` (the landing route), move it out of the module.
3. Create `host/routes.py`:
   ```python
   from fastapi import APIRouter
   from simple_module_hosting.inertia_deps import InertiaDep
   from inertia import InertiaResponse

   router = APIRouter()


   @router.get("/", response_model=None)
   async def landing(inertia: InertiaDep) -> InertiaResponse:
       return await inertia.render("Landing")
   ```
4. In `app_builder.create_app`, after module router mounting, include `host.routes.router` — or, cleaner, expose a Settings-configurable `host_routers: list[APIRouter]` and mount it.
   - Simpler alternative: mount in `host/main.py` via `app.include_router(router)` after `create_app(...)` returns. Pick this; no framework change needed.
5. Move `modules/dashboard/dashboard/pages/Landing.tsx` → `host/client_app/pages/Landing.tsx`. `pages.ts` already scans that directory and keys it as just `"Landing"`.
6. Adjust any tests that hit `/` expecting the dashboard module to own the landing page.

**Verify:** `uv run pytest`; `make dev` and hit `/`, `/dashboard`, menu link.

**Commit:** `fix(dashboard): give dashboard honest /dashboard prefix and host the landing page`

---

## Task 8: Opt-in `TenantMiddleware`

**Files:**
- `framework/hosting/simple_module_hosting/settings.py`
- `framework/hosting/simple_module_hosting/middleware.py`
- `framework/hosting/simple_module_hosting/app_builder.py`
- `framework/hosting/tests/test_app.py`

**Steps:**

1. In `Settings`, add:
   ```python
   multi_tenant: bool = False
   tenant_header: str = ""  # empty disables header-based tenant resolution
   ```
2. In `TenantMiddleware.__init__`, accept `header: str | None = None`; skip the header lookup path when `header` is None or empty.
3. In `app_builder.create_app`, replace the unconditional `app.add_middleware(TenantMiddleware)` with:
   ```python
   if settings.multi_tenant:
       app.add_middleware(TenantMiddleware, header=settings.tenant_header or None)
   ```
4. Update tests: existing multi-tenant tests should pass `Settings(multi_tenant=True, tenant_header="X-Tenant-ID")` in their fixture. Add one new test asserting `TenantMiddleware` is NOT in `app.user_middleware` when `multi_tenant=False`.
5. Add `SM_MULTI_TENANT` and `SM_TENANT_HEADER` stubs (commented) to `.env.example`.

**Verify:** `uv run pytest` — particularly `test_app.py` and any tenant integration tests.

**Commit:** `feat(hosting): make tenant middleware opt-in via SM_MULTI_TENANT`

---

## Task 9: `get_db` skip commit when clean

**Files:** `framework/db/simple_module_db/deps.py`, `framework/db/tests/test_db.py`

**Steps:**

1. Rewrite the success branch:
   ```python
   async with factory() as session:
       try:
           yield session
           has_pending = bool(session.new or session.dirty or session.deleted)
           if has_pending:
               await session.commit()
               op, log_fn = "commit", _db_logger.info
           else:
               await session.rollback()
               op, log_fn = "read_only_rollback", _db_logger.debug
           duration_ms = round((time.perf_counter() - start) * 1000, 2)
           log_fn(
               "db.session.%s" % op,
               extra={"operation": op, "db_duration_ms": duration_ms},
           )
       except Exception:
           await session.rollback()
           ...
   ```
2. Add a test that issues a pure-`SELECT` endpoint request and asserts no COMMIT appears in `pg_stat`. For SQLite tests, assert `session.in_transaction()` is `False` after the dep completes and no commit log line was emitted (use `caplog`).
3. Add a second test that issues a `POST /products/` and asserts the commit path still fires.

**Verify:** full suite — multiple integration tests call `get_db` implicitly. Watch for any test relying on the always-commit behaviour (e.g. expecting state visible to a sibling session before explicit commit — unlikely, but the test might blow up).

**Commit:** `perf(db): skip commit on sessions with no pending writes`

---

## Task 10: Document middleware ordering & conventions

**Files:** `docs/framework-conventions.md` (new)

**Steps:**

1. Create `docs/framework-conventions.md` with sections:
   - **Middleware pipeline** — list order, explain LIFO, and give the concrete framework pipeline.
   - **Module-registered middleware** — rule: peer modules get registered in topological-sort order; LIFO means the last sorted module's middleware wraps outermost. Use `ModuleMeta.depends_on` to express ordering.
   - **Settings conventions** — env-var prefix per module (`SM_<MODULE>_*`); store on `app.state.<module>_settings`; SM012 catches misses.
   - **Database tables** — modules should prefix `__tablename__` for SQLite isolation; PostgreSQL uses schema-per-module automatically (SM_DATABASE_URL-driven).
   - **Inertia page keys** — `{ModuleName}/{PageName}`, where ModuleName is PascalCase and matches `ModuleMeta.name`.
   - **Event naming** — subclass `Event`, declare in `<module>.contracts.events`; subscribers use exact class or any ancestor.
2. Link this doc from the new README (Task 11).

**Verify:** `make lint` still passes (markdown isn't linted; this is just a reminder to not break anything).

**Commit:** `docs: add framework-conventions.md covering middleware, settings, routing`

---

## Task 11: Rewrite `README.md`

**Files:** `README.md`

**Steps:**

1. Structure:
   - One-sentence pitch ("modular monolith framework — FastAPI + Inertia.js + React, with per-module schema isolation and a module lifecycle").
   - **Quickstart** (5 steps): install deps, copy `.env.example`, `make docker-up`, `make migrate`, `make dev`.
   - **Create a module**: `make new-module name=orders`, describe what the scaffold generates.
   - **Architecture** — short tree of `framework/`, `modules/`, `host/`, `packages/`. Link to `docs/framework-conventions.md`.
   - **Common commands table**: `make dev|test|lint|doctor|migrate|new-module`.
   - **Environment variables** — link to `.env.example`; call out `SM_DATABASE_URL`, `SM_AUTH_*`, `SM_MULTI_TENANT`.
   - Links to `docs/plans/` for architectural notes.

**Verify:** read it as if you'd just cloned the repo and see whether steps 1-5 actually work top to bottom.

**Commit:** `docs: write a real README`

---

## Task 12: Full verification pass

**Steps:**

1. `uv sync --all-packages && npm install`
2. `make lint` — clean
3. `make test` — all pass (expect ~231 + the new tests added in tasks above)
4. `make doctor` — exit 0 on a clean tree
5. Manual: `make new-module name=widgets`; `make migrate`; `make dev`; visit `/widgets`, see the sidebar entry, create a widget, confirm it appears on Browse.
6. Manual: set `SM_DATABASE_URL=postgresql+asyncpg://...` (via a throwaway docker-compose profile) and rerun `make migrate && make dev` — the schema should be `widgets`, not `widgets.widgets_widget`.
7. Manual: set `SM_MULTI_TENANT=true, SM_TENANT_HEADER=X-Tenant-ID`; assert queries filter by tenant. Then set `SM_MULTI_TENANT=false` and assert the middleware is gone.

**No commit** — if any step fails, fix in the relevant task's commit or open a follow-up.

---

## Rollout notes

- Tasks 1-6 are pure internal improvements; no deployment impact.
- Task 7 changes `/dashboard` behaviour — if anyone has bookmarks or external links to the current dashboard URLs, audit before rolling out.
- Task 8 default is `multi_tenant=False`. Existing multi-tenant deployments must set `SM_MULTI_TENANT=true` in their env before upgrading, or tenancy filtering will silently disappear. **Flag this in the release notes.**
- Task 9 is a behaviour change visible only in DB profiling. Safe, but worth a release-note line.

---

## Exit criteria

Plan is complete when every checkbox below is true:

- [ ] Task 1-11 each landed in its own commit on the branch.
- [ ] `uv run pytest` green.
- [ ] `make lint` green (`ruff check`, `ruff format --check`, `ty check`, `biome ci`, `tsc`).
- [ ] `make doctor` exits 0 on a clean tree.
- [ ] `README.md` takes a new developer from clone → first module in under 10 minutes.
- [ ] Release notes drafted for Task 8 (opt-in tenancy) and Task 9 (no-op-commit skip).
