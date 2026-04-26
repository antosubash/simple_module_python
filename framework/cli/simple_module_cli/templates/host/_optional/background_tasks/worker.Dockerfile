# Celery worker image for the BackgroundTasks module.
# Serves both the worker and beat services in docker-compose — they
# differ only by command.

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

COPY pyproject.toml uv.lock ./
COPY scripts/ scripts/
COPY client_app/ client_app/

RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app
USER worker

ENV CELERY_APP=scripts.run_worker:celery
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD uv run celery -A $CELERY_APP inspect ping -d celery@$HOSTNAME || exit 1

CMD ["uv", "run", "celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]
