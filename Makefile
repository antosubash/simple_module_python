.PHONY: install install-py install-js dev dev-api dev-ui build test lint doctor migrate migration downgrade migration-history docker-up docker-down kill new-module ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck

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
dev: docker-up
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	uv run --project host uvicorn host.main:app --reload --port 8000

dev-ui:
	npm run dev

# Build
build:
	npm run build

# Testing
test:
	uv run pytest

lint: ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck

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

# Diagnostics
doctor:
	uv run python -m simple_module_hosting.diagnostics

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
