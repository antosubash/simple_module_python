# syntax=docker/dockerfile:1.7
# Celery worker image for the BackgroundTasks module.
#
# Serves both the ``worker`` and ``beat`` services in docker-compose — they
# differ only by command. A separate image (rather than reusing a web one)
# keeps the runtime surface narrow: no Vite, no static assets, no hot-reload
# tooling. uv installs dependencies in the builder only.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY framework/ framework/
COPY modules/ modules/
COPY host/ host/
COPY scripts/ scripts/

# Install the full workspace (all framework + module packages) without dev
# extras. Production workers never need pytest / ruff / ty.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/pyproject.toml /app/pyproject.toml
COPY --from=builder /app/framework /app/framework
COPY --from=builder /app/modules /app/modules
COPY --from=builder /app/host /app/host
COPY --from=builder /app/scripts /app/scripts

# Default ./uploads lives on the shared data volume, as in the app image (#689).
RUN mkdir -p /app/data/uploads \
    && ln -s /app/data/uploads /app/uploads \
    && useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin worker \
    && chown -R worker:worker /app
USER worker
WORKDIR /app

# Beat has no inspect responder; workers ping their own Celery node.
ENV CELERY_APP=scripts.run_worker:celery
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD if tr '\0' '\n' < /proc/1/cmdline | grep -qx beat; then \
        kill -0 1; \
    else \
        celery -A "$CELERY_APP" inspect ping -d "celery@$HOSTNAME"; \
    fi

# Default command is the worker; docker-compose overrides to `beat` for the
# scheduler service.
CMD ["celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]
