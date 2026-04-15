.PHONY: install install-py install-js dev dev-api dev-ui build test test-py test-js lint doctor migrate migration downgrade migration-history docker-up docker-down kill new-module gen-pages sync-module-deps ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-file-size

# Install
install:
	uv sync --all-packages
	npm install

# Install (granular — used by CI so Python jobs don't pull npm and vice versa)
install-py:
	uv sync --all-packages

install-js:
	npm ci

# Development
dev: docker-up gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	uv run --project host uvicorn host.main:app --reload --port 8000

dev-ui:
	npm run dev

# Regenerate host/client_app/modules.{manifest.json,generated.ts,generated.css} from installed modules.
gen-pages:
	uv run --project host sm gen-pages --host-dir=host/client_app

# Install JS deps declared by installed modules into host/client_app/node_modules.
# Wheel-installed modules need this; in-repo workspace modules do not.
sync-module-deps:
	uv run --project host sm sync-js-deps --host-client-app=host/client_app

# Build
build:
	npm run build

# Testing
test: test-py test-js

test-py:
	uv run pytest

test-js:
	npm test

lint: ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-file-size

# Kept granular so pr.yml can run them in parallel.
ci-python-lint:
	uv run ruff format --check .
	uv run ruff check .

ci-python-typecheck:
	uv run ty check

ci-js-lint:
	npx biome ci .

ci-js-typecheck:
	npx tsc --noEmit -p host/client_app/tsconfig.json
	@for cfg in modules/*/tsconfig.json packages/*/tsconfig.json; do \
		[ -f "$$cfg" ] || continue; \
		echo "tsc -p $$cfg"; \
		npx tsc --noEmit -p "$$cfg" || exit 1; \
	done

# Enforce a max of 300 lines per .py/.ts/.tsx file.
# Exempts vendored shadcn components under packages/ui/src/components/ui/**.
ci-check-file-size:
	uv run python scripts/check_file_size.py

# Diagnostics
doctor:
	uv run python -m simple_module_core

# Database migrations
migrate:                    ## Run migrations to head
	cd host && uv run alembic upgrade head

migration:                  ## Create new migration (usage: make migration msg="add foo")
	cd host && uv run alembic revision --autogenerate -m "$(msg)"

downgrade:                  ## Downgrade one revision
	cd host && uv run alembic downgrade -1

migration-history:          ## Show migration history
	cd host && uv run alembic history --verbose

# Scaffolding
new-module:                 ## Scaffold a new module (usage: make new-module name=orders)
	@test -n "$(name)" || (echo "Error: Please provide a module name, e.g. make new-module name=orders" && exit 1)
	uv run python scripts/new_module.py $(name)
	uv sync --all-packages

# Kill dev servers
kill:
	@echo "Stopping dev servers..."
	@-pkill -f "uvicorn host.main" 2>/dev/null
	@-pkill -f "vite" 2>/dev/null
	@-lsof -ti:8000,5173 | xargs kill -9 2>/dev/null
	@echo "Ports 8000 and 5173 freed."

# Docker
docker-up:
	docker compose up -d

docker-down:
	docker compose down
