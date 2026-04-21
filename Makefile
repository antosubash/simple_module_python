.PHONY: install install-py install-js dev dev-api dev-ui build test test-py test-js test-e2e bench memray-run memray-flamegraph loadtest loadtest-memray lint doctor migrate migration downgrade migration-history docker-up docker-down kill new-module gen-pages sync-module-deps ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-file-size worker beat worker-docker

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

test-e2e:                   ## Run end-to-end browser smoke tests (requires `make docker-up` + `make dev` and `uv run playwright install chromium`)
	uv run pytest -m e2e tests/e2e

# Performance
bench:                      ## Run pytest-benchmark suite (tests/benchmarks). Override args with BENCH_ARGS=...
	uv run pytest -m perf --benchmark-enable --benchmark-columns=min,mean,median,max,stddev,ops,rounds $(BENCH_ARGS) tests/benchmarks

# Memory profiling with memray. Point TARGET at any runnable script/module.
# Examples:
#   make memray-run TARGET="-m pytest tests/benchmarks -m perf --benchmark-disable"
#   make memray-run TARGET="scripts/new_module.py demo"
MEMRAY_OUT ?= .memray/profile.bin
TARGET ?= -m pytest tests/benchmarks -m perf --benchmark-disable
memray-run:                 ## Record an allocation profile into $(MEMRAY_OUT)
	@mkdir -p $(dir $(MEMRAY_OUT))
	uv run memray run --force -o $(MEMRAY_OUT) $(TARGET)
	@echo "Profile: $(MEMRAY_OUT) — render with 'make memray-flamegraph'"

memray-flamegraph:          ## Render $(MEMRAY_OUT) as an HTML flamegraph
	uv run memray flamegraph --force $(MEMRAY_OUT)

# Load testing. `make loadtest` assumes `make dev` is running separately.
# `make loadtest-memray` starts uvicorn under memray, runs locust headless,
# shuts down, and emits a flamegraph. Override locust args via LOCUST_ARGS=...
LOCUST_HOST ?= http://localhost:8000
LOCUST_ARGS ?= -u 20 -r 5 -t 30s
loadtest:                   ## Run locust against a server already on $(LOCUST_HOST)
	uv run locust -f tests/loadtest/locustfile.py --host $(LOCUST_HOST) --headless $(LOCUST_ARGS)

loadtest-memray:            ## Start uvicorn under memray, load-test, emit flamegraph
	scripts/loadtest_memray.sh $(LOCUST_ARGS)

lint: ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-file-size ci-check-hardcoded-strings
	uv run python scripts/check_metadata.py
	uv run python scripts/check_readmes.py

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
	@# Fail if a module ships .tsx files but has no tsconfig.json — otherwise
	@# the type-check would silently skip the module. See SM017 in `make doctor`.
	@for dir in modules/*/; do \
		if [ -n "$$(find "$$dir" -name '*.tsx' -print -quit 2>/dev/null)" ] \
			&& [ ! -f "$${dir}tsconfig.json" ]; then \
			echo "error: $$dir has .tsx pages but no tsconfig.json — add one so tsc covers it"; \
			exit 1; \
		fi; \
	done
	@for cfg in modules/*/tsconfig.json packages/*/tsconfig.json; do \
		[ -f "$$cfg" ] || continue; \
		echo "tsc -p $$cfg"; \
		npx tsc --noEmit -p "$$cfg" || exit 1; \
	done

# Enforce a max of 300 lines per .py/.ts/.tsx file.
# Exempts vendored shadcn components under packages/ui/src/components/ui/**.
ci-check-file-size:
	uv run python scripts/check_file_size.py

# Enforce that permissions, role names, Inertia page ids, and module dependency
# names are declared as named constants rather than hardcoded string literals.
ci-check-hardcoded-strings:
	uv run python scripts/check_hardcoded_strings.py

# Diagnostics
doctor:
	uv run python -m simple_module_core

# Database migrations
# All targets run from the repo root so alembic and `make dev-api` share the
# same cwd (and therefore the same .env, SM_DATABASE_URL, and SQLite path).
migrate:                    ## Run migrations to head
	uv run --project host alembic -c host/alembic.ini upgrade heads

migration:                  ## Create new migration (usage: make migration msg="add foo")
	uv run --project host alembic -c host/alembic.ini revision --autogenerate -m "$(msg)"

downgrade:                  ## Downgrade one revision
	uv run --project host alembic -c host/alembic.ini downgrade -1

migration-history:          ## Show migration history
	uv run --project host alembic -c host/alembic.ini history --verbose

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
	@-lsof -ti:8000,5050,5173 | xargs kill -9 2>/dev/null
	@echo "Ports 8000, 5050, 5173 freed."

# Docker
docker-up:
	docker compose up -d postgres redis

docker-down:
	docker compose down

# Celery — local dev (fast reload, no container rebuild)
worker:                     ## Run a Celery worker locally against $(SM_BG_TASKS_BROKER_URL)
	uv run celery -A scripts.run_worker:celery worker -l info

beat:                       ## Run the Celery beat scheduler locally
	uv run celery -A scripts.run_worker:celery beat -l info

# Celery — containerized (matches prod image)
worker-docker:              ## Build + run the worker + beat services in docker
	docker compose up --build worker beat

.PHONY: release-check
release-check:
	@test -n "$(version)" || { echo "usage: make release-check version=X.Y.Z"; exit 1; }
	uv run python scripts/bump_version.py $(version) --check
