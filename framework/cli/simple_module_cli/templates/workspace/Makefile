.PHONY: gen gen-api-types install dev dev-api dev-ui build test test-py test-js lint doctor migrate migration gen-pages sync-module-deps kill gen-i18n

# smpy dev owns both processes and picks the Vite port automatically.
# Override with `make dev ARGS="--port 8010 --vite-port 5201"`.
API_PORT ?= 8000

install:
	uv sync --all-packages
	npm install
	$(MAKE) gen

dev:
	uv run smpy dev $(ARGS)

# --reload-dir keeps the reloader watching in-repo module packages under
# modules/* as well as the host (uvicorn otherwise watches only the launch cwd).
# The reloader watches only *.py unless told otherwise, so --reload-include adds
# the locale catalogs: a reload re-reads them and regenerates the i18n keys.
dev-api:
	cd host && uv run uvicorn main:app --reload --reload-dir . --reload-dir ../modules --reload-include '*locales/*.json' --port $(API_PORT)

dev-ui:
	npm run dev

# Prepare every generated frontend artifact before bundling.
build: gen
	npm run build

# Testing
test: test-py test-js

test-py:
	uv run pytest

# --if-present is a no-op until you add a "test" script (e.g. vitest) to package.json.
test-js:
	npm run test --if-present

# Lint + typecheck (Python). Mirrors the framework's own quality gate.
lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check

# Module diagnostics — the same checks that run at prod boot (orphan pages,
# coupling violations, migration drift, locale issues).
doctor:
	uv run python -m simple_module_core

# Prepare every generated frontend artifact incrementally.
gen:
	uv run smpy gen

gen-api-types:
	uv run smpy openapi gen-types $(ARGS)

# Individual aliases force regeneration, for CI and explicit use.
gen-pages:
	cd host && uv run python -m simple_module_hosting gen-pages --host-dir=client_app

# Pull JS deps shipped by wheel-installed modules into host/client_app/node_modules.
# Root module manifests are npm workspaces; manifests inside Python packages need sync.
sync-module-deps:
	cd host && uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app

# Individual generators remain available; normal install/dev/build use smpy gen.
gen-i18n:
	cd host && uv run python -m simple_module_hosting gen-i18n

# `upgrade heads` (plural) applies every per-module branch head; `upgrade head`
# (singular) errors once a second module adds its own migration branch label.
#
# These run from the repo root, not `cd host`, so alembic and `make dev-api`
# share the same cwd — and therefore the same .env, SM_DATABASE_URL and SQLite
# path. BootstrapSettings reads `.env` relative to the cwd, so running from
# host/ silently migrates the default SQLite DB while the app uses the
# configured one.
migrate:
	uv run --project host alembic -c host/alembic.ini upgrade heads

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	uv run --project host alembic -c host/alembic.ini revision --autogenerate -m "$(msg)"

kill:
	@echo "Stop smpy dev with Ctrl-C (or send SIGTERM to its PID); it cleans up both process groups."
