# syntax=docker/dockerfile:1.7
FROM {{BASE}} AS builder
COPY --from=ghcr.io/astral-sh/uv:python3.12-bookworm /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update{{APT}} \
    && rm -rf /var/lib/apt/lists/*
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-packages --no-dev{{EXTRAS}}

FROM {{BASE}} AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates{{APT_PACKAGES}} \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app /app
RUN mkdir -p /app/data \
    && useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app
WORKDIR /app
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD celery -A scripts.run_worker:celery inspect ping --destination celery@${HOSTNAME} || exit 1
CMD ["celery", "-A", "scripts.run_worker:celery", "worker", "-l", "info"]
