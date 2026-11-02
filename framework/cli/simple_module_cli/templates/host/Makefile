.PHONY: install dev dev-api dev-ui build test test-py test-js lint doctor migrate migration gen-pages sync-js-deps kill gen-i18n

# Dev ports. VITE_PORT follows SM_VITE_DEV_URL in .env (the same value Vite and
# the backend read), falling back to 5050. Override on the command line:
# `make dev API_PORT=8010`. `make kill` frees only these two ports, so other
# apps' dev servers (and vitest runs) on the machine are left alone.
API_PORT ?= 8000
VITE_PORT ?= $(or $(shell sed -n 's/^SM_VITE_DEV_URL=.*:\([0-9][0-9]*\)\/*$$/\1/p' .env 2>/dev/null | tail -n 1),5050)

install:
	uv sync
	cd client_app && npm install
	$(MAKE) sync-js-deps
	$(MAKE) gen-i18n

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	uv run uvicorn main:app --reload --port $(API_PORT)

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

# Regenerate the typed i18n keys (`t(keys.<ns>...)`) into the installed
# @simple-module-py/i18n package. Dev boot does this too; run it after editing a
# locale catalog, before `tsc`, or in CI where nothing boots the app. Fails if
# the package is not installed (run `npm install` first).
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
	@-lsof -ti:$(API_PORT),$(VITE_PORT) | xargs -r kill 2>/dev/null
	@echo "Ports $(API_PORT), $(VITE_PORT) freed."
