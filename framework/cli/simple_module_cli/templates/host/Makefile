.PHONY: install dev dev-api dev-ui build test test-py test-js lint doctor migrate migration gen-pages sync-js-deps

install:
	uv sync
	cd client_app && npm install
	$(MAKE) sync-js-deps

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	uv run uvicorn main:app --reload --port 8000

dev-ui:
	cd client_app && npm run dev

build:
	cd client_app && npm run build

# Testing
test: test-py test-js

test-py:
	uv run pytest

# --if-present is a no-op until you add a "test" script (e.g. vitest) to package.json.
test-js:
	cd client_app && npm run test --if-present

# Lint + typecheck (Python). Mirrors the framework's own quality gate.
lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check

# Module diagnostics — the same checks that run at prod boot (orphan pages,
# coupling violations, migration drift, locale issues).
doctor:
	uv run python -m simple_module_core

gen-pages:
	uv run python -m simple_module_hosting gen-pages --host-dir=client_app

sync-js-deps:
	uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app

# `upgrade heads` (plural) applies every per-module branch head; `upgrade head`
# (singular) errors once a second module adds its own migration branch label.
migrate:
	uv run alembic upgrade heads

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	uv run alembic revision --autogenerate -m "$(msg)"
