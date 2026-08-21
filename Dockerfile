# syntax=docker/dockerfile:1.7
# Default image for the SimpleModule reference app — the host plus every
# bundled module (auth/users, dashboard, permissions, settings, background
# tasks, file storage, feature flags, audit log, branding, site lock).
#
#   docker build -t simple-module-python .
#   docker run --rm -p 8000:8000 simple-module-python
#
# Standalone by design: SQLite under /app/data, no Postgres and no Redis
# needed to boot. `docker-compose.yml`'s `app` service is the same image with
# a named volume; worker/beat (Celery) stay opt-in.
#
# One builder stage carries both uv and Node because the Vite build imports
# `modules.generated.{ts,css}`, which `smpy host gen-pages` emits from the
# *installed Python modules* — a Node-only stage would have nothing to read.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Node 24 — same major as NODE_VERSION in .github/workflows/pr.yml, so the
# image builds the bundle CI validates.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer: every workspace member's manifest, resolved before the
# full source arrives. `uv.lock` is gitignored in this repo, so it's an
# optional glob and the sync deliberately isn't `--frozen`.
COPY pyproject.toml uv.lock* ./
COPY framework/ framework/
COPY modules/ modules/
COPY host/pyproject.toml host/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev --no-install-workspace

# npm workspaces span host/client_app, packages/* and modules/* — every
# member's package.json must exist before `npm ci` will honour the lockfile.
COPY package.json package-lock.json ./
COPY packages/ packages/
COPY host/client_app/package.json host/client_app/
RUN --mount=type=cache,target=/root/.npm npm ci

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev

# Page manifest + generated module imports first, then the production bundle
# into host/static/dist (with its .vite/manifest.json and precompressed
# .gz/.br siblings, which the host serves from the /static mount).
# The venv binary directly rather than `uv run`, which re-resolves and re-syncs
# the environment on every invocation — the layer above already installed
# exactly what this image should contain.
RUN /app/.venv/bin/smpy host gen-pages --host-dir=host/client_app
RUN npm run build

# node_modules is a build-time artifact only; the runtime serves static files.
RUN rm -rf node_modules host/client_app/node_modules

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Containers serve the built bundle; development mode would emit asset tags
# pointing at a Vite dev server that isn't in this image.
ENV SM_ENVIRONMENT=production

# Absolute sqlite path: /app/data is the volume mount point, so the DB is
# cwd-independent and survives restarts whenever a volume is attached.
ENV SM_DATABASE_URL=sqlite+aiosqlite:////app/data/app.db

# Celery refuses a localhost broker in production — that would mean the web
# container talking to its own (absent) 6379. `redis` is the compose service
# name; without that stack the app still boots and only task *dispatch* fails.
ENV SM_BG_TASKS_BROKER_URL=redis://redis:6379/0 \
    SM_BG_TASKS_RESULT_BACKEND=redis://redis:6379/1

# curl backs the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app

RUN mkdir -p /app/data \
    && useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "host.main:app", "--host", "0.0.0.0", "--port", "8000"]
