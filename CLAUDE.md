# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

Python 3.12 + FastAPI + SQLModel + Alembic on the backend; Inertia.js + React + Tailwind 4 + Vite on the frontend. `uv` workspaces for Python, `npm` workspaces for JS. Package managers: `uv sync --all-packages` and `npm install`.

## Local database & services (shared dev-services stack)

**Do NOT start your own Postgres/Redis container.** All repos in `~/Repos` share
one stack defined in `~/Repos/dev-services` (one PostGIS + Redis + MinIO + Adminer
on the `devnet` Docker network). `make docker-up` here brings that shared stack up
(it no longer starts a local postgres/redis); `make docker-down` only stops this
repo's own containers (worker/beat), never the shared stack.

This repo's slice:

- **Postgres**: `localhost:5432`, `postgres`/`postgres`, database
  **`simple_module_python`** (the default `SM_DATABASE_URL` is SQLite; uncomment
  the Postgres line in `.env.example` to use the shared DB).
- **Redis**: `localhost:6379`, logical DBs **4** (broker) / **5** (result backend).

If a port is taken by an old per-project container, stop that container rather
than remapping ports. To add a database, edit `dev-services/init/01-databases.sql`.

## Commands

All day-to-day tasks go through `make`:

| Command | Purpose |
|---|---|
| `make install` | Install Python + JS deps |
| `make dev` | Docker up + regen module pages + API (8000) and Vite (5050) in parallel |
| `make kill` | Free ports 8000/5050/5173 |
| `make test` | Run `test-py` then `test-js` (e2e excluded by default) |
| `make test-py` / `make test-js` | Run a single suite |
| `make test-e2e` | Playwright smoke tests (requires `make dev` running + `uv run playwright install chromium`) |
| `make lint` | Ruff format-check + Ruff + `ty` + Biome + per-workspace `tsc` + 300-line file cap |
| `make doctor` | Module diagnostics (orphan pages, coupling violations, migration drift, locale checks) — same checks run at prod boot |
| `make migrate` / `make migration msg="..."` | Apply / autogenerate Alembic migrations |
| `make new-module name=<name>` | Scaffold a new module package end-to-end |
| `make gen-pages` | Regenerate `host/client_app/modules.{manifest.json,generated.ts,generated.css}` from installed modules |

Single test: `uv run pytest path/to/test_file.py::test_name` (root `pyproject.toml` sets `asyncio_mode=auto` and `-m 'not e2e and not perf'`). A single JS test: `npx vitest run <path>`.

Entry point: `host/main.py` (`uv run --project host uvicorn host.main:app --reload`). Alembic runs from the repo root (`host/alembic.ini`) so it shares the `.env` / `SM_DATABASE_URL` with the API.

## Architecture

This is a **modular-monolith framework**. There is no host–module API boundary: modules are Python packages loaded into one FastAPI app.

**Discovery.** Modules declare `[project.entry-points.simple_module]` in their `pyproject.toml` pointing at a `ModuleBase` subclass. `simple_module_core.discovery.discover_modules()` loads them, topologically sorts by `ModuleMeta.depends_on`, and the host invokes `register_*` hooks in that order. In production (`SM_ENVIRONMENT != development`) discovery is **strict** — any entry-point failure or missing/invalid `meta` raises at boot.

**Module layout** (scaffolded by `make new-module`):
```
modules/<name>/<name>/
├── module.py        # ModuleBase subclass with meta = ModuleMeta(...)
├── models.py        # SQLModel tables
├── contracts/       # SQLModel DTOs (public surface) — add a Protocol only for real extension points
├── service.py       # business logic
├── deps.py          # FastAPI dependencies
├── endpoints/api.py # REST (JSON)
├── endpoints/views.py # Inertia view endpoints
├── pages/*.tsx      # auto-discovered by Vite via modules.generated.ts
├── theme.css        # optional — @theme tokens; imported UNLAYERED
├── styles.css       # optional — component rules; imported into layer(components)
└── locales/<lang>.json
```
Both CSS files are optional and auto-detected; `gen-pages` emits an
`@import "#module/<pkg>/..."` for each, so nothing is added to the host's
`styles.css` by hand. The split is load-bearing: a `@theme` block inside a
cascade layer is inert, while unlayered CSS beats every Tailwind utility —
hence `SM022`/`SM023`. See `docs/module-authoring.md` § Styling.

**Lifecycle hooks** (in `framework/core/simple_module_core/module.py`) — all no-op by default; subclasses override as needed:
`register_settings` → `register_menu_items` / `register_permissions` / `register_feature_flags` / `register_event_handlers` / `register_health_checks` / `register_public_routes` → `register_exception_handlers` → `register_middleware` → `register_routes(api_router, view_router)` → async `on_startup` / `on_shutdown` (reverse order). `register_public_routes(registry)` lets a module exempt anonymous/read-only routes (STAC/OGC, webhooks) from `AuthMiddleware`; rules are method-aware (`registry.add_regex(r"…/tilejson$", methods={"GET"})`), so a GET read route can be public while sibling POST/PATCH mutations under the same prefix stay gated. See [docs/framework/public-routes.md](docs/framework/public-routes.md).

**Middleware pipeline** (Starlette `add_middleware` is LIFO — last added runs first). Execution order on a request:
`(ProxyHeaders, if SM_TRUSTED_PROXY) → CorrelationId → RequestLogging → GZip → SecurityHeaders → Session → <module middleware> → Tenant (opt-in) → Locale → InertiaLayoutData → app`. `GZip` compresses any response over 500 bytes, including the `/static` mount — the built CSS is ~139 KB raw versus ~21 KB gzipped, and uncompressed assets dominated cold page load. `ProxyHeaders` (uvicorn's `ProxyHeadersMiddleware`) is installed only when `SM_TRUSTED_PROXY` is set, sitting outermost so the `X-Forwarded-*`-corrected scheme/client IP reach everything downstream (request logs and Inertia's absolute page url). When two modules add middleware at the same dependency tier, the module that sorts **later** wraps outermost. Use `depends_on` to express relative order — don't rely on names.

**Database**: per-module `Base` via `create_module_base("<name>")`. Every module owns its own `MetaData` (so Alembic autogenerate can attribute tables to a module), but all tables live in the host's single schema. `__tablename__` must be prefixed with the module name to avoid collisions (`orders_order`). Postgres and SQLite share the same layout.

Standard mixins in `simple_module_db.mixins`: `AuditMixin`, `SoftDeleteMixin` (bypass with `stmt.execution_options(include_deleted=True)`), `MultiTenantMixin`, `VersionedMixin`. The per-request session (`get_db`) auto-commits **only if** there are pending writes (via `after_flush` listener); otherwise rollback. Service code should **not** call `session.commit()` — flush if you need DB-assigned values.

**Migrations** live in `host/migrations/versions/` — not in module packages. `host/alembic/env.py` calls `build_module_metadata()` + `make_include_object()` so autogenerate covers every installed module and ignores host-owned tables. First migration of each module should set `branch_labels = ("<module_name>",)` to enable per-module `downgrade <module>@base`.

**Inertia**. `inertia.render("<ModuleName>/<PageName>", ...)` maps to `modules/<name>/<name>/pages/<PageName>.tsx`, where `<ModuleName>` is the PascalCase of the module directory (`blog_posts` → `BlogPosts`). Host-level pages under `host/client_app/pages/` use a bare `<PageName>`. `InertiaLayoutDataMiddleware` populates shared props (`auth`, `menus`, `i18n`); use `InertiaDep` from `simple_module_hosting.inertia_deps`. Mismatched keys fire `SM003` (orphan page) / `SM004` (phantom render).

**CSRF defence**. There is no explicit CSRF token middleware. Protection comes from `SameSite=Lax` on the session cookie (Starlette default): browsers don't attach the cookie to cross-site POST/PUT/DELETE, so a forged form-submit from another origin is unauthenticated. Raw `fetch()` calls in page code don't need a token header.

## Conventions to follow

- **SQLModel is the project-wide standard for every model** — both DB tables (`table=True`) and DTOs (plain `SQLModel` subclasses). Do not use Pydantic `BaseModel` or SQLAlchemy `DeclarativeBase` + `Mapped[...]` in module code.
- **300-line cap** on `.py`/`.ts`/`.tsx` files, enforced by `scripts/check_file_size.py` in CI (exempts vendored shadcn components under `packages/ui/src/components/ui/**`). If you approach the cap, split by responsibility — don't rewrite to squeeze under.
- **Per-module settings**: env-var prefix `SM_<MODULE>_*`, stored on `app.state.<module_lower>` inside `register_settings(app)` as a module-owned dataclass. `SM012` warns if `register_settings` is overridden without adding `app.state.<module_lower>`.
- **Framework vs plugin coupling**: `SM009` is an error if `framework/*` directly imports from a plugin module. Framework code must not reach into `modules/`.
- **Zod schemas with translated messages** must be constructed inside a hook (`useT()`) — never at module scope, or they freeze against the first render's locale.
- **Locales**: ship `<package>/locales/<lang>.json` and declare in `ModuleBase.locale_dirs()` with the module's lowercase name as the namespace. `{"browse": {"title": "X"}}` flattens to `<namespace>.browse.title`. Pluralize with CLDR suffixes (`_one`, `_other`, ...).
- **Ty (type checker) false positives** from SQLModel: `unresolved-attribute`, `unsupported-operator`, `unknown-argument`, `no-matching-overload`, `invalid-argument-type` are all globally ignored in `pyproject.toml` because SQLModel declares fields with plain Python types while runtime instruments them as SQLAlchemy attributes. Do not re-enable these rules — real bugs surface in tests.

## Diagnostic codes

Meaningful codes when reading `make doctor` output: `SM001` missing meta (error), `SM003` orphan page / `SM004` phantom render (warn), `SM007` module overrides no hooks (info), `SM008` duplicate name (error), `SM009` framework→plugin import (error), `SM010` DB revision behind head (error), `SM011` module table not in migration history (warn), `SM012` `register_settings` overridden but nothing on `app.state.<module>` (warn, fires at dev boot only), `SM013`–`SM016` locale issues, `SM017` module ships `.tsx` pages but is missing `package.json`/`tsconfig.json` (warn), `SM018` Inertia `router.{post,patch,put,delete}()` in a page targets a JSON `/api/*` endpoint (warn — Inertia rejects non-Inertia responses), `SM019` module registers view routes (non-empty `view_prefix` + overrides `register_routes`) but overrides neither `register_menu_items` nor `register_permissions` (warn — pages exist with no sidebar entry and no role-editor visibility; admins can't reach them through the UI). Modules whose views are sub-pages of another module typically register permissions to stay discoverable in the role editor without needing their own sidebar entry. `SM020` multiple auth provider modules installed (error), `SM021` no auth provider module installed (warn), `SM022` `@theme`/`@custom-variant`/`@utility` in a module's `styles.css`, where `layer(components)` makes them inert (warn), `SM023` an unlayered rule in a module's `theme.css`, which outranks every Tailwind utility (warn). In production, errors fail boot.

## Tests & fixtures

The `simple_module_test` plugin provides app-level fixtures available to every test directory — auto-loaded via its `pytest11` entry point (defined in `framework/testing/simple_module_test/fixtures.py`), so the root `conftest.py` is intentionally thin:
- `settings` — in-memory SQLite `Settings` with `multi_tenant=True`.
- `db_state`, `engine`, `db_session` — fresh in-memory `DatabaseState` per test; `db_session` also creates all module tables and stamps `alembic_version` at head so the boot-time migration check passes.
- `app` — `create_app(settings)` with lifespan started/stopped.
- `client` / `authenticated_client` — `httpx.AsyncClient`; `authenticated_client` seeds an admin via `users.bootstrap.create_admin` and carries a forged session cookie.

E2E tests live in `tests/e2e/` behind the `e2e` pytest marker and run against a live server — see [docs/e2e-testing.md](docs/e2e-testing.md).

## CI

`.github/workflows/pr.yml` runs Python lint / typecheck / tests, JS lint / typecheck / tests, and the 300-line file-size check as parallel jobs; `make lint` locally runs the same checks serially. Branch protection requires the aggregate `pr-checks` job.

## Authoritative references

When conventions are unclear, these docs are the source of truth (don't reverse-engineer the code):
- [docs/framework-conventions.md](docs/framework-conventions.md) — invariants module authors rely on
- [docs/module-authoring.md](docs/module-authoring.md) — authoring a module for distribution (entry points, migrations, API stability)
- [docs/e2e-testing.md](docs/e2e-testing.md)
- [docs/plans/](docs/plans/) — dated design docs; the most recent is the intended state
