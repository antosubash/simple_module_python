# Default Docker assets for `smpy new` — design

**Date:** 2026-08-06
**Status:** approved (autonomous session — assumptions listed below)

## Goal

Every application created by `smpy new` ships a working container story by
default: a `docker/host.Dockerfile`, a `docker-compose.yml`, a
`.dockerignore`, and `make docker-up` / `make docker-build` targets — for
every preset, both DB choices, and both layouts (workspace + flat).

Today Docker assets appear only when the `background_tasks` module is
selected, via its recipe. A default `smpy new myapp` (standard preset)
produces no Docker files at all. The optional templates are also broken for
real apps: the frontend stage never runs `gen-pages`, so the Vite build
fails on the missing `modules.generated.{ts,css}`, and `worker.Dockerfile`
copies `client_app/` from the root — a path that only exists in flat mode.

## Decisions

1. **Docker emission moves to an always-run scaffold step** —
   `simple_module_cli/docker_assets.py`, called from `create_app_project`
   after module recipes. It knows the resolved module selection, so it can
   compose the right service set in one place. The `background_tasks`
   recipe no longer writes compose/Dockerfiles (it keeps `run_worker.py`,
   the broker env keys, and its Make targets).
2. **One image for app, worker, and beat.** The workspace venv already
   contains everything (`uv sync --all-packages`), so worker/beat services
   build the same `docker/host.Dockerfile` with a different `command:`.
   `worker.Dockerfile` is deleted from the templates.
3. **Dockerfile follows the proven smpy_saas pattern** (the only known
   working containerisation of a SimpleModule app): a
   `ghcr.io/astral-sh/uv:python3.12-bookworm` builder stage with Node 22
   installed runs `uv sync --all-packages` → `npm ci` → `smpy gen-pages` →
   `vite build` → re-sync (so hatch force-include picks up `static/dist`);
   a `python:3.12-slim-bookworm` runtime stage copies `.venv` + sources,
   runs as a non-root user, healthchecks `GET /health`, and starts with
   `alembic upgrade heads` (plural — singular errors once a second module
   ships its own branch label) before uvicorn.
4. **Compose matches the scaffold's `--db` choice.** Migration histories
   are dialect-frozen at autogenerate time (`sa.false()` compiles to
   `DEFAULT 0` on SQLite, which Postgres rejects — found by booting a real
   scaffold), so a sqlite scaffold's containers stay on SQLite (named
   volume at `/app/data`) and only `--db postgres` scaffolds get a
   `postgres` service (db/user matching `.env.example`:
   `postgres`/`postgres`, db = kebab-case app slug). All app containers set
   `SM_ENVIRONMENT=production` (a container has no Vite dev server;
   development mode would emit asset tags pointing at `localhost:5050`).
   Selecting `background_tasks` appends `redis`, `worker`, and `beat`
   service fragments plus the `redisdata` volume — and injects the broker
   URLs into the *app* service too, whose `BackgroundTasksSettings`
   otherwise fails production boot on the localhost default.
5. **Compose is assembled from fragments** (per-DB `services` base +
   optional per-DB tasks services + a computed `volumes:` block) rather
   than merged YAML, keeping the templates dumb and the logic in one small
   Python function. `smpy new` also generates real
   `SM_USERS_RESET_PASSWORD_TOKEN_SECRET` /
   `SM_USERS_VERIFICATION_TOKEN_SECRET` values into `.env.example` (like
   `SM_SECRET_KEY`), because `UsersSettings` refuses its placeholder
   secrets in production.
6. **Flat mode gets a flat variant Dockerfile** (`npm install` inside
   `client_app/`, no `cd host`). Flat is legacy but should not silently
   lose the default.

## Assumptions (would normally be clarifying questions)

- "Application" means the `smpy new` scaffold (not `make new-module`
  modules, which are libraries and don't run standalone).
- Even sqlite-selected apps get the Postgres-backed compose: sqlite is the
  zero-config *local dev* default, but a containerised deployment should
  not write its database into an ephemeral container layer.
- The shared `~/Repos/dev-services` stack convention is a rule for this
  workspace's own repos, not for scaffolded apps shipped to other users —
  a self-contained compose is the correct default for the scaffold.

## Testing

- New `framework/cli/tests/test_cli_docker_assets.py`: default scaffold
  emits compose/Dockerfile/dockerignore/Make targets; compose contains
  `postgres` + `app` only; bg-tasks selection adds redis/worker/beat and
  reuses `host.Dockerfile`; flat mode emits the flat variant; db name is
  substituted.
- `test_cli_new.py` / `test_cli_recipes.py` updated: `worker.Dockerfile`
  is gone; the recipe no longer owns compose.
- `docker compose config` validation of a scaffolded app's compose file
  (cheap, no image pulls) as part of manual verification.
