# Deployment

A production deployment is one FastAPI process (plus optional Celery workers) behind a reverse proxy, backed by Postgres and Redis. Nothing exotic — standard 12-factor plumbing.

## Production checklist

Before serving traffic:

- [ ] `SM_ENVIRONMENT` set to something other than `development`/`testing` (those two are the only values treated as non-prod).
- [ ] `SM_SECRET_KEY` is a strong random value (not the default).
- [ ] `SM_DATABASE_URL` points at Postgres (`postgresql+asyncpg://`), not SQLite.
- [ ] `alembic upgrade heads` run against the production DB.
- [ ] Frontend built (`npm run build` → `static/dist/`) and bundled into the image — outside `development`/`testing`, the app renders assets from the Vite manifest, not a dev server (see [Static assets](#static-assets)).
- [ ] App boot in a non-development `SM_ENVIRONMENT` starts clean. Module discovery runs strict (missing/invalid `meta` and entry-point failures raise), and the migration check (SM010) aborts boot — so a successful start covers those. The full page/locale/auth-provider diagnostic suite only runs in development, so do a clean dev boot before shipping (see [diagnostic codes](/reference/diagnostic-codes)).
- [ ] Admin bootstrap complete — an admin user exists and can log in.
- [ ] Reverse proxy forwards `X-Forwarded-Proto`/`X-Forwarded-For`; configured with `--proxy-headers`.
- [ ] HTTPS in front of the app (the session cookie is `HttpOnly`/`SameSite=Lax` but not `Secure` by default — terminate TLS at the proxy).
- [ ] Log destination configured (`SM_LOG_FORMAT=json` + log shipping).

## Build

**Every `smpy new` scaffold ships its own Docker assets** — you don't write these by hand:

| Path | What it is |
|---|---|
| `docker/host.Dockerfile` | Multi-stage app image (also used for the Celery worker/beat services) |
| `docker-compose.yml` | Stack matched to your `--db` choice, plus `redis`/`worker`/`beat` when `background_tasks` is installed |
| `.dockerignore` | Keeps `node_modules`, caches and local state out of the build context |
| `make docker-build` / `docker-up` / `docker-down` | Build, run and stop the stack |

```bash
make docker-up   # builds the image, applies migrations, serves on :8000
```

The compose file pins `SM_ENVIRONMENT=production` for the app service — a container has no Vite dev server, so development mode would emit asset tags pointing at nothing.

::: warning `SM_ENVIRONMENT=production` doesn't make the default stack production-ready
A default (SQLite) scaffold's compose file also pins `SM_DATABASE_URL=sqlite+aiosqlite:////app/data/app.db`, which fails the second item in the checklist above. That stack is for local and demo runs — a real deployment wants a `--db postgres` scaffold.

The reason it isn't just a URL swap: a migration history is **dialect-frozen at autogenerate time** (`sa.false()` renders as `DEFAULT 0` under SQLite, which Postgres rejects), so containers must run the same dialect the migrations were generated against. Moving an existing SQLite scaffold to Postgres means regenerating migrations against Postgres, not editing one env var.
:::

### Why the image has one builder stage

The obvious split — a Python stage and a Node stage — **cannot work here**. The Vite build imports `modules.generated.{ts,css}`, which `gen-pages` emits by inspecting the *installed Python modules*. A Node-only stage has no venv and no entry points, so it can't generate those files and the frontend build fails for any app with module pages.

So `docker/host.Dockerfile` keeps uv and Node in one builder stage and orders the work:

1. `uv sync --all-packages --no-dev` (deps first, then the real source, for layer caching)
2. `gen-pages` — writes the page manifest and generated module imports
3. `npm run build` — the production bundle
4. `uv sync` once more, so hatch `force-include` picks up freshly built module `static/dist` output

The runtime stage is `python:3.12-slim-bookworm`, runs as a non-root `app` user (uid 10001), and carries a `HEALTHCHECK` against `/health`.

If you build your own image instead, keep that ordering — skipping `gen-pages` before the Vite build is the single most common way to get a container that builds cleanly and then serves a blank page.

### Sizing the web process

The shipped `CMD` runs a single Uvicorn worker. Tune worker count with `--workers N` for multi-CPU boxes, or run behind a process manager like Gunicorn with Uvicorn workers. A single worker is CPU-bound (one process, the GIL) — multiple workers scale read throughput roughly linearly on a multi-core box.

**Size the DB pool to the worker count.** Each worker keeps its own connection pool of up to `SM_DB_POOL_SIZE + SM_DB_MAX_OVERFLOW` (default `10 + 20 = 30`) connections, so the deployment's ceiling is `workers × (pool_size + max_overflow)`. Keep that under the database's `max_connections` (Postgres default `100`) or workers will throw `asyncpg.TooManyConnectionsError: sorry, too many clients already` under load. For example, 4 workers want roughly `SM_DB_POOL_SIZE=5`, `SM_DB_MAX_OVERFLOW=10` (≤ 60 connections). For larger fleets, put PgBouncer in front instead of growing every pool.

### Migrations on container start

The shipped `CMD` runs `alembic upgrade heads && uvicorn …`. Note **`heads` (plural)**: each module's first migration sets its own `branch_labels`, so once a second module ships one, `upgrade head` (singular) errors out.

That default is right for a single container. Once you run more than one replica, move migrations to a one-shot job instead — see [Running migrations on deploy](#running-migrations-on-deploy).

## Running migrations on deploy

Once you run more than one replica, drop the `alembic upgrade heads` from the container's start command — concurrent replicas racing the same migration is exactly the failure it causes. Run it as a **one-shot job** before rolling the web tier instead:

```bash
# one-shot container — run from the host project (default workspace scaffold)
cd host && uv run alembic upgrade heads

# then roll web tier
kubectl rollout restart deployment/web
```

The boot-time migration check (`SM010`) will fail cleanly if web starts against an unmigrated DB.

## Process topology

For small deployments, one web container is plenty. Scale by adding:

- **Web replicas** — stateless; they share state via DB and Redis. Session cookies are signed, so any replica can serve any request.
- **Celery workers** — `SM_MODULES_ENABLED=background_tasks,<modules with tasks>` keeps workers lean. Run `uv run celery -A scripts.run_worker:celery worker -l info`.
- **Celery beat** (scheduler) — exactly one instance, separate deployment.

## Observability

### Logs

`SM_LOG_FORMAT=json` emits structured logs. Every line has a `correlation_id` (set by `CorrelationIdMiddleware`). Shipping to a central store (Loki / CloudWatch / Datadog) lets you trace a request across web and worker.

### Health checks

- `/health` — returns 200 with `{"status": "healthy", "migration": ...}` (includes the cached migration state). No dependency checks.
- `/health/live` — Kubernetes liveness. Returns 200 `{"status": "alive"}` if the process is up.
- `/health/ready` — readiness. Runs every module's registered health checks concurrently and aggregates the worst status into the JSON body (`healthy`/`degraded`/`unhealthy`). Returns 200 regardless — inspect the `status` field rather than the HTTP code.

### Metrics

Not built in. The framework doesn't expose Prometheus metrics out of the box. If you need them, wrap `uvicorn` with `prometheus-fastapi-instrumentator` in your host bootstrap — it auto-scrapes endpoint latency/count.

## Session cookie

`SessionMiddleware` uses `SM_SECRET_KEY` for signing. Starlette's defaults apply: `HttpOnly` + `SameSite=Lax`, but **not** `Secure` (the framework adds the middleware with only `secret_key`, so the cookie isn't restricted to HTTPS — rely on your TLS-terminating proxy). Rotate the secret by:

1. Deploying with a new `SM_SECRET_KEY`.
2. Expected behavior: existing sessions become invalid. Users sign back in.

There's no built-in key-rollover mechanism — if you need zero-downtime session rotation, fork `SessionMiddleware` to accept a list of keys (first = active, rest = verify-only).

## CSRF

Relies on `SameSite=Lax`. Browsers don't attach the cookie to cross-site POST/PUT/DELETE, so forged submissions land unauthenticated and get rejected at the permission check. No token middleware, no per-form token.

**Caveat:** `SameSite=Lax` does attach on top-level navigations. If you have state-changing GETs (you shouldn't — but), that's an attack surface. Keep side effects out of GET handlers.

## Reverse proxy

Minimum nginx:

```nginx
upstream app { server app:8000; }

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # TLS config here

    location / {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Start `uvicorn` with `--proxy-headers` so it trusts `X-Forwarded-For` for client IP logging.

## Static assets

The Vite build outputs to `static/dist/` (the app mounts the `static/` dir at `/static`, so built assets live under `/static/dist/`). Serve these via the reverse proxy directly (not through Uvicorn) for better performance:

```nginx
location /static/ {
    alias /var/www/app/static/;
    access_log off;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

Vite emits filenames with content hashes, so long cache TTLs are safe.

### Production rendering & cache headers

Outside `development`/`testing` (i.e. any other `SM_ENVIRONMENT`), the app serves the built frontend instead of the Vite dev server:

- **Manifest-based Inertia rendering.** In dev/testing the page loads `main.tsx` from the Vite dev server; otherwise the app reads the built Vite manifest and emits content-hashed `<script>`/`<link>` tags. At boot it normalises the raw Vite manifest (`static/dist/.vite/manifest.json`) into `static/dist/.vite/inertia-manifest.json`, re-keying the entry chunk to the path fastapi-inertia expects. If the build directory is read-only (e.g. an immutable container layer) it writes that normalised copy to a temp file instead. If **no** built manifest is found it logs a warning and leaves assets unconfigured rather than crashing — so a missing `npm run build` surfaces as broken asset URLs, not a boot failure. Build the frontend before serving production traffic.
- **Immutable cache headers, even through Uvicorn.** The app mounts `static/` with a `StaticFiles` subclass that sets `Cache-Control: public, max-age=31536000, immutable` on anything under `/static/dist/assets/` (Vite content-hashes those filenames, so the bytes for a URL never change). Non-hashed paths keep the default `ETag`/`Last-Modified`. Fronting `/static/` with nginx (above) is still recommended for throughput, but the immutable headers are correct even when assets are served straight from the app.

## Zero-downtime deploys

1. Build new image.
2. Run `alembic upgrade heads` as a one-shot job.
3. `kubectl rollout restart deployment/web` (rolling).
4. Watch logs for `SM010` (would mean step 2 failed silently).
5. Rollback path: `kubectl rollout undo`; old pods come back up against the new DB. **Make sure** your migrations are backward-compatible for at least one release cycle (expand/contract pattern — see below).

### Expand / contract migrations

- Add a new column **nullable** in release N.
- Release N+1: start writing to the new column, still read from both.
- Release N+2: stop reading the old column; make the new one NOT NULL.
- Release N+3: drop the old column.

Each release is deployable on its own. Each rollback goes to a compatible previous release.

## Disaster recovery

- **DB backups** — Postgres point-in-time recovery via WAL archiving. Standard RDS / Cloud SQL options cover this.
- **Secrets** — `SM_SECRET_KEY` must be recoverable from your secrets manager. Rotating it invalidates all sessions but doesn't break anything else.
- **Sessions** — lost sessions mean users re-login; acceptable.
- **Uploads** — the `file_storage` module's `filesystem` backend is ephemeral. For production, point it at S3 or a network filesystem and back that up independently.

## Publishing releases

See [docs/release.md](/release) for the full Python + JS publishing flow (OIDC Trusted Publishing on PyPI, `NPM_TOKEN` on npm, driven from GitHub Actions).
