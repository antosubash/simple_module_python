.PHONY: install dev dev-api dev-ui build test test-py test-js lint doctor migrate migration gen-pages sync-module-deps kill

install:
	uv sync --all-packages
	npm install
	$(MAKE) sync-module-deps

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

# --reload-dir keeps the reloader watching in-repo module packages under
# modules/* as well as the host, so edits to a module's routes/endpoints/
# locales hot-reload too (uvicorn otherwise watches only the launch cwd).
dev-api:
	cd host && uv run uvicorn main:app --reload --reload-dir . --reload-dir ../modules --port 8000

dev-ui:
	npm run dev

build:
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

# Regenerate host/client_app/modules.{manifest.json,generated.ts,generated.css}
# from installed modules (workspace + wheel-installed).
gen-pages:
	cd host && uv run python -m simple_module_hosting gen-pages --host-dir=client_app

# Pull JS deps shipped by wheel-installed modules into host/client_app/node_modules.
# Workspace modules under modules/* don't need this — npm hoists them automatically.
sync-module-deps:
	cd host && uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app

# `upgrade heads` (plural) applies every per-module branch head; `upgrade head`
# (singular) errors once a second module adds its own migration branch label.
migrate:
	cd host && uv run alembic upgrade heads

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	cd host && uv run alembic revision --autogenerate -m "$(msg)"

kill:
	@-pkill -f "uvicorn main:app" 2>/dev/null
	@-pkill -f vite 2>/dev/null
	@-lsof -ti:8000,5050 | xargs kill -9 2>/dev/null
	@echo "Ports 8000, 5050 freed."
