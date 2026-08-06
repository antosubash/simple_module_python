# syntax=docker/dockerfile:1.7
# App image for a flat-layout SimpleModule host (`smpy new --flat`).
#
# One builder stage holds both uv and Node: the Vite build imports
# modules.generated.{ts,css}, which `smpy gen-pages` emits from the
# *installed Python modules* — so the frontend cannot build in a
# Node-only stage. The same image also serves the celery worker/beat
# services (background_tasks): docker-compose swaps the command.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Node 22 for the Vite build.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Warm the third-party dep layer before copying the full source.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Flat mode keeps the frontend's own package.json under client_app/.
RUN cd client_app && if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Page manifest + generated module imports, then the production bundle.
RUN uv run python -m simple_module_hosting gen-pages --host-dir=client_app
RUN cd client_app && npm run build

# node_modules never ships in the runtime image.
RUN rm -rf node_modules client_app/node_modules

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app

# /app/data backs the SQLite named volume (harmless for Postgres apps).
RUN mkdir -p /app/data \
    && useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# `upgrade heads` (plural) applies every per-module migration branch;
# `upgrade head` (singular) errors once a second module ships its own
# branch label.
WORKDIR /app
CMD ["sh", "-c", "alembic upgrade heads && uvicorn main:app --host 0.0.0.0 --port 8000"]
