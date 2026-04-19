# Celery worker image for the BackgroundTasks module.
#
# Serves both the ``worker`` and ``beat`` services in docker-compose — they
# differ only by command. A separate image (rather than reusing a web one)
# keeps the runtime surface narrow: no Vite, no static assets, no hot-reload
# tooling. Everything needed is ``uv sync`` + the project source.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Dependency-only layer so code changes don't bust the wheel cache.
COPY pyproject.toml uv.lock ./
COPY framework/ framework/
COPY modules/ modules/
COPY host/ host/
COPY scripts/ scripts/

# Install the full workspace (all framework + module packages) without dev
# extras. Production workers never need pytest / ruff / ty.
RUN uv sync --all-packages --frozen --no-dev

# Drop privileges. uv writes to /app/.venv so it needs write access until
# sync completes; chown after install to keep the build step rootful.
RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app
USER worker

# Container-native healthcheck: ask the worker to ping itself via Celery's
# control protocol. Fails fast if the worker has crashed but the PID lingers.
ENV CELERY_APP=scripts.run_worker:celery
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD uv run celery -A $CELERY_APP inspect ping -d celery@$HOSTNAME || exit 1

# Default command is the worker; docker-compose overrides to `beat` for the
# scheduler service.
CMD ["uv", "run", "celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]
