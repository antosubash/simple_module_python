# Introduction

**simple_module_python** is a modular-monolith framework for Python. You ship one FastAPI app, but the features live in separate Python packages called *modules* — each with its own database tables, HTTP endpoints, React pages, permissions, and tests. At boot, the framework discovers every installed module via Python entry points and composes them into a single running application.

You get the distribution benefits of microservices — teams can own a module, ship it as a wheel, upgrade independently — without paying the runtime cost of service-to-service RPC, API-client codegen, and distributed-transaction gymnastics.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI (Starlette underneath) |
| ORM | SQLModel (SQLAlchemy async + Pydantic) |
| Migrations | Alembic |
| Frontend bridge | Inertia.js |
| Frontend | React 19 + Tailwind CSS 4 + Vite |
| Auth | fastapi-users (local email+password, cookie sessions) |
| Tooling | uv (Python), npm (JS), Ruff, ty, Biome, pytest, Playwright |

## When to reach for this

Reach for simple_module_python when:

- You are building a single product with multiple distinct domains (billing, users, catalog, CRM) that you want to keep isolated but not over-networked.
- You want server-rendered pages with React ergonomics, not a split SPA ↔ REST-API codebase.
- You want the option to distribute modules as packages later without rewriting them.
- You would reach for Django but find its admin and ORM too opinionated and its async story still half-baked.

## When **not** to reach for this

- You need a pure async REST API with no UI and no session state — a vanilla FastAPI project is lighter.
- You need multi-tenant isolation at the database level across separate DB hosts — this project uses row-level `MultiTenantMixin`, not tenant-per-cluster.
- Your team already has a working Django monolith and doesn't need module-level distribution.

## Design pillars

### 1. No host–module API boundary

Modules are Python packages loaded into one process. They call each other directly (via imported services), not over HTTP. That means:

- No OpenAPI generation between internal modules.
- No circuit-breakers or retry policies for internal calls.
- Refactors that cross modules are regular Python refactors — caught by the type checker and test suite at compile time.

The public surface **between** modules is a module's `contracts/` directory: SQLModel DTOs and domain events. Modules depending on another import only from that module's top-level package and its `contracts` subpackage — never reach into its `service.py` internals.

### 2. Convention-first, with diagnostics

The framework enforces conventions — page naming, settings prefixes, migration branches, locale key structure — through a diagnostics pass (`make doctor`). Violations produce `SM0XX` codes; errors fail boot in production. This replaces runtime surprises with build-time guarantees.

See [diagnostic codes](/reference/diagnostic-codes) for the full list.

### 3. SQLModel everywhere

SQLModel is the project-wide standard for *every* model — DB tables (`table=True`) **and** DTOs (plain `SQLModel` subclasses). We don't use plain Pydantic `BaseModel`, and we don't use SQLAlchemy's `DeclarativeBase` + `Mapped[...]` style. One type system, one set of gotchas, one mental model.

### 4. Inertia over split SPAs

React pages are served from Python endpoints via Inertia. The middleware attaches shared props (`auth`, `menus`, `i18n`) to every response, so components get the data they need without bespoke `/api/me` calls. Page discovery is file-system based — drop a `.tsx` file under `modules/<name>/<name>/pages/` and it's live.

## Next steps

- [Install](/guide/installation) the dev environment.
- [Quickstart](/guide/quickstart) — bootstrap and boot the sample app in 5 minutes.
- [Project structure](/guide/project-structure) — understand where code lives before touching anything.
- [Your first module](/guide/first-module) — end-to-end walk-through.
