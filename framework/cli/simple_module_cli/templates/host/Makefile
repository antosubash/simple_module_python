.PHONY: gen gen-api-types install dev dev-api dev-ui build test test-py test-js lint doctor migrate migration gen-pages sync-js-deps kill gen-i18n

# smpy dev owns both processes and picks the Vite port automatically.
# Override with `make dev ARGS="--port 8010 --vite-port 5201"`.
API_PORT ?= 8000

install:
	uv sync
	cd client_app && npm install
	$(MAKE) gen

dev:
	uv run smpy dev $(ARGS)

dev-api:
	uv run uvicorn main:app --reload --reload-include '*locales/*.json' --port $(API_PORT)

dev-ui:
	cd client_app && npm run dev

# Prepare every generated frontend artifact before bundling.
build: gen
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

gen:
	uv run smpy gen

gen-api-types:
	uv run smpy openapi gen-types $(ARGS)

gen-pages:
	uv run python -m simple_module_hosting gen-pages --host-dir=client_app

sync-js-deps:
	uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app

# Individual generators remain available; normal install/dev/build use smpy gen.
gen-i18n:
	uv run python -m simple_module_hosting gen-i18n

# `upgrade heads` (plural) applies every per-module branch head; `upgrade head`
# (singular) errors once a second module adds its own migration branch label.
migrate:
	uv run alembic upgrade heads

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	uv run alembic revision --autogenerate -m "$(msg)"

kill:
	@echo "Stop smpy dev with Ctrl-C (or send SIGTERM to its PID); it cleans up both process groups."
