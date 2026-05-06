# FastAPI host image. Multi-stage: Node builds the Vite client bundle,
# Python serves uvicorn. Migrations run on container start.

FROM node:22-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
COPY host/client_app/package.json host/client_app/
COPY modules/ modules/
RUN npm ci --workspaces --include-workspace-root
COPY host/ host/
RUN npm --workspace host/client_app run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock* ./
COPY host/pyproject.toml host/
COPY modules/ modules/
RUN uv sync --all-packages --no-dev

COPY host/ host/
COPY --from=frontend /app/host/static/dist host/static/dist

RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "cd host && uv run alembic upgrade head && uv run uvicorn main:app --host 0.0.0.0 --port 8000"]
