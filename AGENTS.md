# AGENTS.md

Guidance for coding agents (Claude Code, Codex, Cursor, OpenCode, …) working in this
repository. It holds what changes how code gets written here; history and rationale live
in `docs/`. Claude Code reads it through `CLAUDE.md`, which adds a few Claude-only rules.

## What this is

A **modular-monolith framework**: feature modules are Python packages loaded into
one FastAPI app, each with its own SQLModel tables, REST + Inertia endpoints and
React pages. There is no host–module API boundary.

Stack: Python 3.12 + FastAPI + SQLModel + Alembic; Inertia.js v3 + React +
Tailwind 4 + Vite. `uv` workspaces for Python, `npm` workspaces for JS.
Published as ~24 PyPI packages (`simple_module_*`) and 4 npm packages
(`@simple-module-py/*`) in lockstep (`docs/release.md`).

Layout: `framework/{core,db,hosting,inertia,testing,cli,remote}` (the framework),
`modules/<name>` (plugin modules), `host/` (the dev host app and all Alembic
migrations), `packages/{ui,i18n,tsconfig,vite-plugin}` (shared JS), `skills/` (agent skills
shipped to users via `smpy skills add`), `.claude/skills/` (skills for this repo).

## Commands

Everything goes through `make`; the root `Makefile` is the full list
(`docs/reference/make-commands.md` documents the *scaffolded app's* Makefile, not this one).

| Command | Purpose |
|---|---|
| `make install` | `uv sync --all-packages` + `npm install` + `smpy gen` |
| `make dev` | Shared Docker stack up (needs the sibling `../dev-services` checkout), then `smpy dev`: generation + API (:8000) + Vite (first free port from 5050). Without Docker, run `uv run smpy dev` |
| `make test` / `make test-py` / `make test-js` | Pytest (SQLite, e2e/perf excluded; parallel via `pytest-xdist`, `-n $(PYTEST_WORKERS) --dist loadgroup`, default 4 workers, `PYTEST_WORKERS=0` for serial) then Vitest |
| `make test-py-pg` | Pytest on Postgres (`SM_TEST_DATABASE_URL`, default db `sm_test`); parallel like `test-py`, each xdist worker creates its own `sm_test_gw<N>` database (role needs `CREATEDB`); not in `pr-checks` |
| `make test-e2e` | Playwright smoke tests against a running `make dev` |
| `make lint` | Every CI lint check: Ruff format + Ruff + `ty` + Biome + host/module `tsc`, package metadata/README, locale files, doc paths, i18n and API-type freshness, file-size cap, no test sleeps, no double casts, no raw `fetch`, hardcoded strings, CI parity, untranslated strings |
| `make doctor` | Module diagnostics (`SM0xx`) |
| `make migrate` / `make downgrade` / `make migration-history` | Alembic `upgrade heads` / `-1` / history |
| `make migration LABEL=<branch_label> msg="..."` | Autogenerate on the selected branch (`--head <branch_label>@head`); `LABEL` is required |
| `make migrations-roundtrip-pg` | Postgres portability gate (upgrade → downgrade base → upgrade → `alembic check`); CI runs it |
| `make gen` | Incrementally generate pages, i18n keys, module JS deps and API types; also runs during install/dev/build and `smpy module verify` |
| `make gen-pages` | Regenerate `host/client_app/modules.{manifest.json,generated.ts,generated.css}` (gitignored; needed before `tsc`/Vite) |
| `make gen-i18n` | Regenerate module-local and app-owned i18n keys plus central compatibility files (committed; CI checks freshness) |
| `make gen-api-types` | Regenerate each module's `pages/api.generated.ts` from its routes (committed; CI diffs via `ci-api-types-fresh`) |
| `make new-module name=<name>` | Scaffold a module package (see § Adding a module for what it does *not* do) |
| `make openapi` | Export `openapi.json` for typed clients |
| `make worker` / `make beat` | Celery worker / beat for `background_tasks` |

Single tests: `uv run pytest path/to/test_file.py::test_name` from the repo root
(`asyncio_mode=auto`, `-m 'not e2e and not perf'` are set in `pyproject.toml`;
`-n` is passed by `make test-py`, not by `addopts`, so this runs in-process);
`npx vitest run <path>` for JS. Entry point: `host/main.py`
(`uv run --project host uvicorn host.main:app --reload`). Alembic runs from the
repo root via `host/alembic.ini`, so it shares `.env`/`SM_DATABASE_URL` with the API.

### Local environment

- **No env var is required.** The default DB is SQLite (`./app.db`), so tests and
  a plain local run need no services. `make dev` starts the author's *shared*
  dev-services stack from `../dev-services/compose.yml` (Postgres on
  `localhost:5432`, db `simple_module_python`; Redis on `localhost:6379`, one
  `SM_REDIS_URL=redis://localhost:6379/4` seeds broker and backend). Never start
  your own Postgres/Redis containers; `make docker-down` only stops this repo's
  worker/beat.
- **Sandboxed sessions have no Docker.** Launch API + Vite directly per
  `.claude/skills/running-the-stack/SKILL.md` (spare ports, SQLite file DB,
  `smpy users create-admin`). Use `uv run smpy dev --port 8201` for a spare
  API port; Vite is chosen automatically, or pin it with `--vite-port 5201`.
  Ctrl-C/SIGTERM stops only the process groups this supervisor started.
  `make kill` prints this stop guidance; it never searches by process name or port.
- The test plugin ignores project dotenv files; leave `.env` in place.
  Never export `SM_ENVIRONMENT=production` in a shell that
  runs pytest: production validators (localhost broker, placeholder secrets)
  abort the test plugin.
- The invalidation tests need `redis-server` on `PATH` or `SM_TEST_REDIS_URL`;
  without either they skip locally and **fail** when `CI` is set.

## Before you push

Run what CI runs, in this order; a red push costs a review cycle.

1. `make gen` once per fresh checkout and after route/catalog changes.
   Page manifests are gitignored; commit regenerated i18n keys and API types.
   The incremental cache is local to the checkout; CI freshness targets still
   run generators unconditionally. `tsc` and Vite need the generated files.
2. `make lint`. `ruff format --check .` also formats Python fences inside
   `.md` files, so run `uv run ruff format docs/` after editing docs. Every
   backticked repo path in `AGENTS.md`, `CLAUDE.md`, `README.md`, `.agents/rules/`,
   `docs/` and `skills/` must be a tracked file (`scripts/check_doc_paths.py`;
   exceptions in `scripts/doc_path_allowlist.txt`).
3. `make test-py` and `make test-js`.
4. Touched any `locales/*.json`? `make gen-i18n` and commit the generated
   files; CI runs the generator and fails on a diff. The generator refuses to
   drop a namespace (an unsynced venv looks like a deleted module);
   `make gen-i18n ARGS=--allow-removals` is only for a module you really
   removed or a deliberate `SM_MODULES_ENABLED` subset.
   Changed an endpoint's response shape in a module that has `pages/api.generated.ts`?
   `make gen-api-types` and commit it. Don't write `as unknown as` in shipped
   TS (`ci-check-no-double-cast`); mark an unavoidable one `// cast-ok: <reason>`.
5. Added a module, a table or a migration? Also run `make doctor`, and review
   the revision per `docs/module-authoring.md` § Reviewing a revision
   autogenerated on SQLite (boolean `server_default` as `sa.true()/sa.false()`,
   expression indexes by hand, enum downgrades via `drop_enums_if_postgres`).
   `make migrations-roundtrip-pg` proves Postgres portability against a
   disposable DB; where no Postgres is available, skip it and let CI run it.
6. User-visible change? Add a `## [Unreleased]` entry to `CHANGELOG.md` (Keep a
   Changelog; cite issue numbers and migration revision ids; mark behaviour
   changes).

CI (`.github/workflows/pr.yml`, aggregate job `pr-checks`): python-lint (the
`make lint` checks above that are not JS), docs-build (`make ci-docs-build`,
the VitePress site), python-typecheck, python-tests (Redis service), js-tests,
js-lint (`biome ci --error-on-warnings`, plus the untranslated check),
js-typecheck (plus `make ci-api-types-fresh`), js-build (`make ci-css-build`),
migrations-roundtrip-pg, doctor (`make ci-doctor`: migrate a throwaway SQLite
DB, `alembic check`, then `make doctor`), e2e-smoke, perf-guards,
file-size-check, package-build, docker-smoke (`make ci-docker-smoke`: build and
boot the production image, check health and a rendered asset; path-filtered on PRs).
CI calls the same `make ci-*` targets as
`make lint` (`make ci-check-ci-parity` enforces it), with
`UV_SYNC_FLAGS=--locked` so a stale `uv.lock` fails: commit `uv.lock` whenever a
`pyproject.toml` changes (`make install` stays unlocked). `make ci-css-build`,
`make ci-docs-build` and `make ci-docker-smoke` are in CI but not in `make lint` (slow).
`.github/workflows/postgres-tests.yml` runs `make test-py-pg` nightly, on
demand and on PRs touching `framework/db`, `framework/testing`,
`modules/{tenants,users,background_tasks,file_storage}` or `host/migrations`;
it is not in `pr-checks`. e2e-smoke and perf-guards enable a hardcoded
`SM_MODULES_ENABLED` JSON list; a new module is not exercised there until added.

## Detailed rules

Domain-specific rules live in flat `.agents/rules/*.md` files so each instruction
file stays under Antigravity CLI's 24 KB rule limit (read the relevant file when
working in that area; `CLAUDE.md` imports only `AGENTS.md`):

| File | Scope |
|---|---|
| `.agents/rules/architecture.md` | Module discovery, layout, lifecycle hooks, middleware order, admin surfaces, Inertia, CSRF |
| `.agents/rules/database.md` | Module `Base`, mixins, `AwareDateTime`, SQLite/Postgres sessions, tenancy, Alembic migrations |
| `.agents/rules/conventions.md` | Module/UI/i18n/API coding conventions and styling rules |
| `.agents/rules/testing.md` | `simple_module_test` fixtures, SQLite/Postgres parity, xdist, and E2E setup |

## Adding a module or package

There is **one scaffolder**: `make new-module name=<name>` runs
`scripts/new_module.py`, a thin wrapper over the CLI's
`simple_module_cli.scaffold.scaffolding.create_module(..., framework_repo=True)`, the same
templates `smpy create-module` / `smpy new` use
(`framework/cli/simple_module_cli/templates/module/`). Change a convention there, once.

Settings plumbing is opt-in: `smpy create-module --with-settings` or
`make new-module name=<name> ARGS=--with-settings` adds DB-backed settings,
a services container and `register_settings`; the default omits them.

It generates a CRUD sample (model, DTOs, service, REST + Inertia endpoints,
Browse/Create/Edit pages, `locales/en.json`, tests) that passes `make lint`,
wires the module into `host/pyproject.toml`, the root `testpaths`/`extra-paths`
and the `publish-pypi` matrix in `release.yml`, and runs `uv sync --all-packages`,
`npm install`, `make gen-i18n` and `smpy openapi gen-types --module <name>`.
Commit the resulting `uv.lock`, `package-lock.json`,
`packages/i18n/src/{keys.generated,generated-resources}.ts` and
`pages/api.generated.ts`. It does **not**:

1. Create a migration for the sample table: edit `models.py`, then follow
   `.agents/rules/database.md` (`--head <label>@head`, set `branch_labels` on
   the first revision). `make doctor` reports `SM011` until you do.
2. Register a PyPI pending publisher for the new `simple_module_<name>`
   (manual; the release leg 403s without it).
3. Write `docs/modules/<name>.md`, add it to `docs/modules/index.md` and the
   VitePress sidebar in `docs/.vitepress/config.ts`.
4. Add a `CHANGELOG.md` entry, or add the module to the e2e/perf
   `SM_MODULES_ENABLED` lists if those jobs should exercise it.

A new `framework/*` package is wired by hand: root `pyproject.toml`
`testpaths` + `[tool.ty.environment].extra-paths` and the `publish-pypi`
matrix. A new `packages/*` npm package goes into the `publish-npm` matrix.
Unlisted test directories are silently never collected.

## Diagnostics

`make doctor` and a development boot run the `SM0xx` checks; a dev boot adds
`SM012` and `SM031` (they need the built app), and `SM025` runs at boot in every
environment. The table with triggers and fixes is
`docs/reference/diagnostic-codes.md`. **Production does not run the suite.**
What fails a production boot is strict discovery (a bad entry point, missing
`meta`, duplicate meta names, or a missing `depends_on` target), the auth-provider check
(`SM020`), placeholder secrets, a localhost Celery broker, the `SM010`
migration check (except on a never-migrated first run, which goes to `/setup`),
overlapping `spa_mounts` (`SM032`) and an `error` from a module's
`check_data_compatibility` (`SM033`). Catch everything else with `make doctor`
before shipping. Codes that change how you write code: `SM003`/`SM004`
render-key mismatch, `SM009` framework→plugin import, `SM011` table missing from
migrations, `SM012` settings not on `app.state`, `SM013`–`SM016` locale drift,
`SM017` invalid optional frontend dependency manifests, `SM018` Inertia
call to `/api`, `SM019` views with no menu item or permission, `SM022`/`SM023`
CSS in the wrong file, `SM024` unique key without `tenant_id`, `SM028` heavy
import in `tasks.py`, `SM031` `/api` route with no permission/`Authenticated()`
gate and not public, `SM034` `subscribe_durable` without `name=`.

## Working in parallel

Split work into independent slices and run them at once: verification of claims
against code, surveys across many files, test runs per package and adversarial
review are all parallel-safe. Keep sequential what depends on an earlier result.
Give each slice its goal, what is already ruled out, the files to read and the
exact output wanted, and treat every report as claims to verify. Never let two
agents write to one working tree: give a writing agent its own `git worktree`.

## Repo skills

`skills/*/SKILL.md` are the agent skills this repo **ships to users**
(`smpy skills add`, `npx skills add antosubash/simple_module_python`); when a
convention in this file changes, update the matching skill in the same PR.
`.claude/skills/running-the-stack/SKILL.md` is the verified recipe for launching
the stack in a sandbox.

## Authoritative references

When conventions are unclear, read these instead of reverse-engineering code:
`docs/framework-conventions.md` (invariants), `docs/module-authoring.md`
(entry points, migrations, API stability), `docs/framework/*.md` (lifecycle,
middleware, settings, events, i18n, tenancy), `docs/database/*.md`,
`docs/testing/*.md`, `docs/reference/*.md` (make commands, env vars,
diagnostic codes), `docs/superpowers/specs/` (canonical design docs) and
`docs/superpowers/plans/` (implementation plans). `docs/plans/` is historical;
follow status banners and current reference docs rather than dates alone.
