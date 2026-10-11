---
name: running-the-stack
description: Use when launching, restarting, or smoke-testing simple_module_python locally — the FastAPI host API (uvicorn) and the Vite dev server for the Inertia/React client — or when a local run fails to start, a port is taken, or login fails.
---

# Running simple_module_python

## Prerequisites (once per checkout / worktree)
- `uv sync --all-packages && npm install && make gen-pages` — a fresh worktree has no `.venv`, no `node_modules` and no generated pages; skipping this fakes unrelated lint/test failures.
- Postgres/Redis are the SHARED stack in `~/Repos/dev-services` (`make docker-up` starts it). Never start your own containers. Default DB is SQLite, so a plain local run needs neither.
- No `.env` is required. If one exists, read it (don't copy values) — `.env` beats process env for `SM_VITE_DEV_URL`.

## Launch (verified 2026-10-09, SQLite, spare ports 8201/5201)
| Step | Command |
|---|---|
| Check ports free | `ss -ltn \| grep -E ':(8201\|5201) '` (empty = free) |
| DB + migrations | `export SM_DATABASE_URL=sqlite+aiosqlite:///./dev-tmp.db` then `uv run --project host alembic -c host/alembic.ini upgrade heads` |
| Admin login | `uv run smpy users create-admin --email admin@example.com --password <choose-one> --force` |
| Frontend (background) | `SM_VITE_PORT=5201 npm run dev` |
| Backend (background) | `SM_DATABASE_URL=sqlite+aiosqlite:///./dev-tmp.db SM_VITE_DEV_URL=http://localhost:5201 uv run --project host uvicorn host.main:app --port 8201` |
| Everything on default ports | `make dev` — API :8000 + Vite :5050, also runs `docker-up` + `gen-pages` *(unverified this session)* |

## Ready check
- `curl -fsS http://localhost:8201/health` → 200 (about 20 s after start).
- App: `http://localhost:8201/` · sign in at `/users/login` with the admin you created · admin area `/admin`.
- Anonymous `curl` of an app page 302s to the login page; that is expected.

## Stop / reset
- Kill every PID listening on your ports: `ss -ltnp | grep -E ':(8201|5201) '` then `kill <pid> …`. `uv run … uvicorn` spawns a child, and a `--workers N` server leaves workers bound if you only kill one PID.
- `command rm -f dev-tmp.db* < /dev/null`.

## Gotchas
- Ports 8000/5050 are often held by OTHER projects on this machine (a foreign Vite will hydrate this HTML with the wrong bundle). Use spare ports; check `/proc/<pid>/cwd` before killing anything you didn't start.
- Never `pkill -f "uvicorn … --port N"` — the pattern matches your own shell. `make kill` runs `pkill -f vite`, which also kills other projects' Vite servers; prefer killing by port.
- A wrong `E2E_PASSWORD` trips the login rate limiter (5 failures / 300 s) and cascades into 429 timeouts.
- `cp`/`rm` are interactive aliases in this shell: use `command cp -f` / `command rm -f … < /dev/null`.

## Tests
- Unit: `make test-py` (move any `.env` aside first — a dashboard test asserts Vite on :5050) · `make test-js` · single: `uv run pytest path::name`, `npx vitest run <path>`.
- Postgres: `SM_TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sm_test uv run pytest -p no:anyio <paths>`.
- E2E (server running): `uv run playwright install chromium` once, then `E2E_BASE_URL=http://localhost:8201 E2E_USERNAME=admin@example.com E2E_PASSWORD=<pw> uv run pytest -m e2e tests/e2e -v`. See `docs/e2e-testing.md`.
- Gate before a PR: `make lint` (also format-checks Python in `.md` — run `uv run ruff format docs/` first).
