# Deployment

A production deployment is one FastAPI process (plus optional Celery workers) behind a reverse proxy, backed by Postgres and Redis. Nothing exotic — standard 12-factor plumbing.

## Production checklist

Before serving traffic:

- [ ] `SM_ENVIRONMENT` set to something other than `development`/`testing` (those two are the only values treated as non-prod).
- [ ] `SM_SECRET_KEY` is a strong random value (not the default).
- [ ] `SM_DATABASE_URL` points at Postgres (`postgresql+asyncpg://`), not SQLite.
- [ ] `alembic upgrade head` run against the production DB.
- [ ] App boot in a non-development `SM_ENVIRONMENT` starts clean. Module discovery runs strict (missing/invalid `meta` and entry-point failures raise), and the migration check (SM010) aborts boot — so a successful start covers those. The full page/locale/auth-provider diagnostic suite only runs in development, so do a clean dev boot before shipping (see [diagnostic codes](/reference/diagnostic-codes)).
- [ ] Admin bootstrap complete — an admin user exists and can log in.
- [ ] Reverse proxy forwards `X-Forwarded-Proto`/`X-Forwarded-For`; configured with `--proxy-headers`.
- [ ] HTTPS in front of the app (the session cookie is `HttpOnly`/`SameSite=Lax` but not `Secure` by default — terminate TLS at the proxy).
- [ ] Log destination configured (`SM_LOG_FORMAT=json` + log shipping).

## Build

Typical Docker build for an app scaffolded by `smpy new`:

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY . .
RUN uv run python -m compileall .

# Build the frontend
FROM node:20-slim AS frontend
WORKDIR /app/client_app
COPY client_app/package.json client_app/package-lock.json ./
RUN npm ci
COPY client_app .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app /app
# Vite builds to ../static/dist relative to client_app, i.e. /app/static/dist
COPY --from=frontend /app/static/dist /app/static/dist
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
```

Tune worker count with `--workers N` for multi-CPU boxes, or run behind a process manager like Gunicorn with Uvicorn workers. A single worker is CPU-bound (one process, the GIL) — multiple workers scale read throughput roughly linearly on a multi-core box.

**Size the DB pool to the worker count.** Each worker keeps its own connection pool of up to `SM_DB_POOL_SIZE + SM_DB_MAX_OVERFLOW` (default `10 + 20 = 30`) connections, so the deployment's ceiling is `workers × (pool_size + max_overflow)`. Keep that under the database's `max_connections` (Postgres default `100`) or workers will throw `asyncpg.TooManyConnectionsError: sorry, too many clients already` under load. For example, 4 workers want roughly `SM_DB_POOL_SIZE=5`, `SM_DB_MAX_OVERFLOW=10` (≤ 60 connections). For larger fleets, put PgBouncer in front instead of growing every pool.

## Running migrations on deploy

Don't migrate from inside the web container's startup hook — that way lies races when scaling up. Run it as a **one-shot job** before rolling the web tier:

```bash
# one-shot container — run from the host project (default workspace scaffold)
cd host && uv run alembic upgrade head

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

## Zero-downtime deploys

1. Build new image.
2. Run `alembic upgrade head` as a one-shot job.
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
