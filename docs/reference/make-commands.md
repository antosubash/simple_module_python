# Make commands

Everything day-to-day flows through `make`. The `Makefile` at the repo root is the interface — if it isn't a `make <target>`, it isn't a routine operation.

## Setup & install

| Command | What |
|---|---|
| `make install` | `uv sync --all-packages` + `npm install`. Safe to re-run — picks up new packages and entry points. |
| `make doctor` | Static analysis: orphan pages, coupling violations, migration drift, locale consistency. Same checks run at prod boot. Exits non-zero on errors. |

## Dev

| Command | What |
|---|---|
| `make dev` | `make docker-up` + regen module pages + API (`uvicorn` on `:8000`) + Vite (`:5050`) in parallel. |
| `make kill` | Free ports 8000, 5050, 5173. Useful when `make dev` crashed and left orphans. |
| `make gen-pages` | Regenerate `host/client_app/modules.{manifest.json,generated.ts,generated.css}` from installed modules. Auto-runs before `make dev`. |
| `make sync-module-deps` | Install JS deps declared by wheel-installed modules into `host/client_app/node_modules`. In-repo workspace modules don't need this. |
| `make docker-up` | Start the Postgres + Redis containers defined in `docker-compose.yml`. |
| `make docker-down` | Stop them. |

## Test

| Command | What |
|---|---|
| `make test` | `make test-py` then `make test-js`. E2E excluded. |
| `make test-py` | `uv run pytest` — the root config pins `-m 'not e2e'` and `asyncio_mode=auto`. |
| `make test-js` | `npx vitest run --passWithNoTests`. |
| `make test-e2e` | Playwright smoke suite. Requires `make dev` already running and `uv run playwright install chromium` done once. |

Single test: `uv run pytest path/to/test_file.py::test_name`. Single Vitest file: `npx vitest run <path>`.

## Lint & typecheck

`make lint` runs the whole battery serially; CI runs them as parallel jobs. The aggregate `pr-checks` job is the required status check on `main`.

| Step | Tool | What it catches |
|---|---|---|
| Format | Ruff | Python format drift |
| Lint | Ruff | Python style / common bugs |
| Type | ty | Python type errors (SQLModel false positives are globally suppressed) |
| Lint/format | Biome | JS/TS lint + format in one pass |
| Type | tsc | Per-workspace `tsc --noEmit` |
| Size | `scripts/check_file_size.py` | 300-line cap on `.py`/`.ts`/`.tsx` (exempts vendored shadcn under `packages/ui/src/components/ui/**`) |

Run a single step on its own:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run ty check .`
- `npx biome check .`
- `npm run typecheck`

## Migrations

| Command | What |
|---|---|
| `make migrate` | `alembic upgrade head`. Idempotent. |
| `make migration msg="add orders tables"` | `alembic revision --autogenerate -m "..."`. Review the file before committing. |

Downgrade (no dedicated make target):

```bash
uv run alembic downgrade -1                 # one step back
uv run alembic downgrade <rev_id>           # to a specific revision
uv run alembic downgrade orders@base        # uninstall one module
```

## Scaffolding

| Command | What |
|---|---|
| `make new-module name=orders` | Generate `modules/orders/` with the full layout, register the entry point, re-run `uv sync`. |

After scaffolding, edit `models.py`, run `make migration msg="add orders tables"`, review, `make migrate`, restart `make dev`.

## Background tasks

The `background_tasks` module ships a Celery worker + beat scheduler. Redis from `make docker-up` is the default broker.

| Command | What |
|---|---|
| `make worker` | Run a Celery worker locally (`celery -A scripts.run_worker:celery worker`). Reloads on code change. |
| `make beat` | Run the Celery beat scheduler locally. |
| `make worker-docker` | Build + run the worker + beat services via `docker compose` (matches prod image). |

The admin UI exposes a worker status page at `/background-tasks/workers` for live worker / queue introspection.

## Performance & load testing

| Command | What |
|---|---|
| `make bench` | Run the `pytest-benchmark` suite under `tests/benchmarks` (perf marker). Override with `BENCH_ARGS=...`. |
| `make memray-run TARGET="..."` | Record an allocation profile into `$(MEMRAY_OUT)` (default `.memray/profile.bin`). `TARGET` can be any runnable script/module — defaults to the benchmark suite. |
| `make memray-flamegraph` | Render `$(MEMRAY_OUT)` as an HTML flamegraph. |
| `make loadtest` | Run Locust headless against a server already on `$(LOCUST_HOST)` (default `http://localhost:8000`). Override duration/users with `LOCUST_ARGS="-u 20 -r 5 -t 30s"`. |
| `make loadtest-memray` | Start uvicorn under memray, run a load test, shut down, emit a flamegraph. |

## Common compositions

Pre-commit sanity:

```bash
make lint && make test
```

Reset a stuck dev loop:

```bash
make kill && rm app.db && make migrate && make dev
```

Full repro of a CI run locally:

```bash
make install && make lint && make test && make doctor
```

Clean up and start fresh Postgres:

```bash
make kill && make docker-down && docker volume rm simple_module_python_pgdata
make docker-up && make migrate && make dev
```

## Tips

- `make -j` can parallelize independent targets, but the supplied targets already parallelize where useful (`dev`, CI jobs).
- `make -n <target>` prints the commands without running them — great for understanding what a composite target does.
- The Makefile is short and readable — open it when a target's behavior surprises you.

## Next steps

- [Environment variables](/reference/env-vars) — every `SM_*` knob the framework reads.
- [Diagnostic codes](/reference/diagnostic-codes) — what each `SM0XX` from `make doctor` means and how to fix it.
- [Deployment](/reference/deployment) — taking a build from `make dev` to production.
