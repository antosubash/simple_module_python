---
name: running-the-stack
description: Use when launching, restarting, or smoke-testing simple_module_python locally — the FastAPI host API and Vite dev server — or when a local run fails to start, a port is taken, or login fails.
---

# Running simple_module_python

## Prerequisites (once per checkout / worktree)
- Run `~/.codex/bin/wait-for-headroom` before servers, browsers or suites. Keep at most two heavy jobs and one full suite; cap pytest workers at eight.
- `make install` installs Python + npm dependencies and runs the incremental generation pipeline. A fresh worktree needs generated frontend files before typechecking or Vite. `uv run smpy gen` refreshes pages, i18n keys, module JS dependencies and API types without rewriting unchanged files.
- Postgres/Redis are the SHARED stack in `~/Repos/dev-services` (`make docker-up` starts it). Never start your own containers. Default DB is SQLite, so a plain local run needs neither.
- No dotenv file is required. Do not read credential files. Python loads the project dotenv file; exported variables take precedence. Configuration belongs in DB settings; the dev URL is process wiring.

## Launch (SQLite, spare API port)
| Step | Command |
|---|---|
| DB + migrations | `export SM_DATABASE_URL=sqlite+aiosqlite:///./dev-tmp.db` then `uv run --project host alembic -c host/alembic.ini upgrade heads` |
| Admin login | `uv run smpy users create-admin --email admin@example.com --password <choose-one> --force` |
| API + frontend | `uv run smpy dev --port 8201` |
| Fixed frontend port if needed | `uv run smpy dev --port 8201 --vite-port 5201` |
| Shared services + API/frontend | `make dev ARGS="--port 8201"` (requires Docker and the sibling dev-services checkout) |

`smpy dev` runs generation first, chooses the first free Vite port from 5050 (unless pinned), prints both URLs, and passes one `SM_VITE_DEV_URL` to API and Vite. Pin spare ports with `uv run smpy dev --port 8201 --vite-port 5201`. An explicitly occupied port fails. For direct launches, set `SM_VITE_DEV_URL=http://localhost:5201` for both the API and `npm run dev`; the Vite config derives its port and origin from that URL.

## Ready check
- Poll `curl -fsS http://localhost:8201/health` until 200, with a deadline; inspect logs on failure.
- App: `http://localhost:8201/` · sign in at `/users/login` with the admin you created · admin area `/admin`.
- Anonymous requests to app pages may 302 to login; that is expected.

## Stop / reset
- Ctrl-C in the supervisor terminal, or `kill -TERM <supervisor-pid>` if launched in the background. Wait for exit. It stops only its owned process groups, including Vite/npm and uvicorn reload workers; either child exiting stops the sibling too.
- Never use process-name or port searches to kill servers. `make kill` now prints supervisor stop guidance.
- Remove a disposable SQLite file only after the supervisor stops and only if this run created it.

## Gotchas
- API port 8000 is often held by another project. Use `--port 8201`; Vite chooses a spare port itself. Do not kill an unknown listener.
- A wrong `E2E_PASSWORD` trips the login rate limiter (5 failures / 300 s) and cascades into 429 timeouts.
- `cp`/`rm` are interactive aliases in this shell: use `command cp -f` / `command rm -f … < /dev/null`.
- No live launch was performed for the supervisor implementation; its port and cleanup behavior is covered with subprocess stubs.

## Tests
- Unit: `make test-py PYTEST_WORKERS=8` (project dotenv files are ignored) · `make test-js` · single: `uv run pytest path::name`, `npx vitest run <path>`.
- Postgres: `SM_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sm_test uv run pytest -p no:anyio <paths>`.
- E2E (server running): `uv run playwright install chromium` once, then `E2E_BASE_URL=http://localhost:8201 E2E_USERNAME=admin@example.com E2E_PASSWORD=<pw> uv run pytest -m e2e tests/e2e -v`. See `docs/e2e-testing.md`.
- Gate before a PR: `make lint` (also format-checks Python in Markdown; run `uv run ruff format docs/` after editing docs).
