.PHONY: install install-py install-js dev dev-api dev-ui build test test-py test-py-pg test-js test-e2e bench memray-run memray-flamegraph loadtest loadtest-seed loadtest-memray bench-nav lint doctor migrate migration downgrade migration-history migrations-roundtrip-pg docker-up docker-down kill new-module gen-pages openapi gen-i18n docker-build docker-app docker-compose-app sync-module-deps ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-file-size ci-check-test-sleeps ci-check-no-double-cast ci-check-hardcoded-strings ci-check-untranslated ci-check-metadata ci-check-locales ci-doc-paths ci-docs-build ci-i18n-fresh ci-css-build ci-doctor ci-build-packages worker beat worker-docker

# UV_SYNC_FLAGS is empty locally; CI passes --locked so a stale uv.lock fails the build.
UV_SYNC_FLAGS ?=

# Install
install:
	uv sync $(UV_SYNC_FLAGS) --all-packages
	npm install

# Install (granular — used by CI so Python jobs don't pull npm and vice versa)
install-py:
	uv sync $(UV_SYNC_FLAGS) --all-packages

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

# Export the OpenAPI document (/api/** only) to openapi.json, no server needed.
openapi:
	uv run --project host smpy openapi export --out openapi.json

# Regenerate host/client_app/modules.{manifest.json,generated.ts,generated.css} from installed modules.
gen-pages:
	uv run --project host smpy host gen-pages --host-dir=host/client_app

# Regenerate packages/i18n/src/{generated-resources,keys.generated}.ts from every
# installed module's locales/, plus host/locales and the hosting package's ui_locales — without
# booting the app. Pass flags with ARGS, e.g. `make gen-i18n ARGS=--allow-removals`.
gen-i18n:
	uv run --project host python scripts/gen_i18n.py $(ARGS)

# Install JS deps declared by installed modules into host/client_app/node_modules.
# Wheel-installed modules need this; in-repo workspace modules do not.
sync-module-deps:
	uv run --project host smpy host sync-js-deps --host-client-app=host/client_app

# Build
build:
	npm run build

# Testing
test: test-py test-js

# Parallel via pytest-xdist (#524): every fixture builds its own in-memory
# SQLite app, so tests share nothing across worker processes. Not in addopts,
# so a single `uv run pytest path::test` still runs in-process without paying
# for worker start-up. PYTEST_WORKERS=0 runs serially (e.g. under a debugger).
# loadgroup keeps tests marked `xdist_group(...)` on one worker (shared repo
# tree, module-scoped subprocess stacks); everything else is load-balanced.
PYTEST_WORKERS ?= auto
test-py:
	uv run pytest -n $(PYTEST_WORKERS) --dist loadgroup

# The Python suite on Postgres (#343). Needs an empty database the tests may
# drop and recreate `public` in. `-p no:anyio`: tests marked
# `@pytest.mark.anyio` would otherwise run on anyio's event loop while the
# async fixtures ran on pytest-asyncio's, and an asyncpg connection cannot
# cross loops (aiosqlite's thread hides this on SQLite). asyncio_mode=auto
# still runs those tests. Serial on purpose: every test drops and recreates
# `public` in the one database, so parallel workers would wipe each other's.
SM_TEST_PG_URL ?= postgresql+asyncpg://postgres:postgres@localhost:5432/sm_test
test-py-pg:
	SM_TEST_DATABASE_URL=$(SM_TEST_PG_URL) uv run pytest -p no:anyio

test-js:
	npm test

test-e2e:                   ## Run end-to-end browser smoke tests (requires `make docker-up` + `make dev` and `uv run playwright install chromium`)
	uv run pytest -m e2e tests/e2e

# Performance
bench:                      ## Run pytest-benchmark suite (tests/benchmarks). Override args with BENCH_ARGS=...
	uv run pytest -m perf --benchmark-enable --benchmark-columns=min,mean,median,max,stddev,ops,rounds $(BENCH_ARGS) tests/benchmarks

# Navigation benchmark — click-to-paint for Inertia client-side navigations.
# Separate from `bench` because it needs a live server and a browser, whereas
# `bench` runs in-process. Point PERF_BASE_URL at the server under test and set
# PERF_BUILD=dev|prod so the report records which build produced the numbers.
PERF_ROUNDS ?= 20
PERF_BUILD ?= dev
bench-nav:                  ## Navigation benchmark (needs a running server + `uv run playwright install chromium`)
	PERF_ROUNDS=$(PERF_ROUNDS) PERF_BUILD=$(PERF_BUILD) uv run pytest -m "perf and e2e" tests/perf -v -s

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
# Run `make loadtest-seed` once beforehand to fill the DB (faker) with realistic
# volumes — set SM_DATABASE_URL to a THROWAWAY database first. Override row
# counts via SEED_ARGS="5000 50000" (users, audit). See tests/loadtest/README.md.
LOCUST_HOST ?= http://localhost:8000
LOCUST_ARGS ?= -u 20 -r 5 -t 30s
loadtest-seed:              ## Seed realistic faker data into $$SM_DATABASE_URL (users + audit)
	uv run python tests/loadtest/seed.py $(SEED_ARGS)


loadtest:                   ## Run locust against a server already on $(LOCUST_HOST)
	uv run locust -f tests/loadtest/locustfile.py --host $(LOCUST_HOST) --headless $(LOCUST_ARGS)

loadtest-memray:            ## Start uvicorn under memray, load-test, emit flamegraph
	scripts/loadtest_memray.sh $(LOCUST_ARGS)

lint: ci-python-lint ci-python-typecheck ci-js-lint ci-js-typecheck ci-check-metadata ci-check-locales ci-doc-paths ci-i18n-fresh ci-check-file-size ci-check-test-sleeps ci-check-no-double-cast ci-check-hardcoded-strings ci-check-untranslated

# Kept granular so pr.yml can run them in parallel.
ci-python-lint:
	uv run ruff format --check .
	uv run ruff check .

ci-python-typecheck:
	uv run ty check

ci-js-lint:
	npx biome ci --error-on-warnings .

ci-js-typecheck: gen-pages
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
	@for cfg in modules/*/tsconfig.json packages/*/tsconfig.json framework/*/tsconfig.json; do \
		[ -f "$$cfg" ] || continue; \
		echo "tsc -p $$cfg"; \
		npx tsc --noEmit -p "$$cfg" || exit 1; \
	done

ci-check-locales:
	uv run python scripts/check_locales.py

# Package metadata, release matrix, ty extra-paths / pytest testpaths (#520), and READMEs.
ci-check-metadata:
	uv run python scripts/check_metadata.py
	uv run python scripts/check_readmes.py

# Every backticked repo path in the user docs must exist (#519).
ci-doc-paths:
	uv run python scripts/check_doc_paths.py

# The VitePress site must build (docs/ is not an npm workspace; own lockfile).
ci-docs-build:
	cd docs && npm ci && npm run build

# The checked-in typed-key files must match what the installed modules' catalogs
# emit. Catches a catalog edit committed without regenerating, and (with the
# namespace guard in gen_i18n.py) a regeneration that dropped keys.
# Compares content before/after regeneration rather than `git diff`, so a locally
# regenerated-but-unstaged file passes and a stale one fails (CI checks out clean).
ci-i18n-fresh:
	@before=$$(find packages/i18n/src -type f | sort | xargs cat | sha256sum); \
	uv run --project host python scripts/gen_i18n.py || exit 1; \
	after=$$(find packages/i18n/src -type f | sort | xargs cat | sha256sum); \
	if [ "$$before" != "$$after" ]; then \
		echo "packages/i18n/src was stale and has been regenerated: run 'make gen-i18n' and commit the result"; \
		exit 1; \
	fi

# Drives a real gen-pages + vite build to prove module CSS and cross-module npm
# imports resolve. Needs node_modules; slow and rewrites generated files, so it
# is not part of `lint`.
ci-css-build:
	uv run pytest framework/cli/tests/test_module_css_build.py

# Enforce a max of 300 lines per .py/.ts/.tsx file.
# Exempts vendored shadcn components under packages/ui/src/components/ui/**.
ci-check-file-size:
	uv run python scripts/check_file_size.py

# Fail on a fixed sleep(<non-zero>) in a test without `# intentional-sleep: <reason>`;
# poll with simple_module_test.wait_for instead.
ci-check-test-sleeps:
	uv run python scripts/check_test_sleeps.py

# Fail on `as unknown as` in shipped TS (pages, components, packages/ui, host client)
# without `// cast-ok: <reason>`; use typed page args or usePageProps instead.
ci-check-no-double-cast:
	uv run python scripts/check_no_double_cast.py

# Enforce that permissions, role names, Inertia page ids, and module dependency
# names are declared as named constants rather than hardcoded string literals.
ci-check-hardcoded-strings:
	uv run python scripts/check_hardcoded_strings.py

# Fail when a .tsx renders user-visible text as a literal instead of t(keys.…).
# Shipping locales/en.json never proved a page actually read it: SM013-SM016
# only compare catalogs to each other, so with i18n_supported_locales=["en"]
# they never fire and tsc is happy with hardcoded English.
ci-check-untranslated:
	node scripts/check_untranslated_strings.mjs

# Dry-run the release build: build sdists + wheels for every workspace member
# the same way release.yml does. Catches packaging regressions at PR time
# (e.g. force-include paths that crash the sdist→wheel rebuild) instead of
# only when someone clicks "Run workflow" on Releases.
ci-build-packages:
	rm -rf dist-py-ci
	uv build --all-packages --out-dir dist-py-ci
	rm -rf dist-py-ci

# Diagnostics
doctor:
	uv run python -m simple_module_core

# Throwaway SQLite DB: migrate to heads, then run the SM0xx suite against it
# (the same checks that fail a production boot). Not in `lint`: it needs a DB.
CI_DOCTOR_DB ?= ci-doctor.db
ci-doctor:
	rm -f $(CI_DOCTOR_DB)
	SM_DATABASE_URL=sqlite+aiosqlite:///./$(CI_DOCTOR_DB) $(MAKE) migrate \
		&& SM_DATABASE_URL=sqlite+aiosqlite:///./$(CI_DOCTOR_DB) $(MAKE) doctor; \
		rc=$$?; rm -f $(CI_DOCTOR_DB)*; exit $$rc

# Database migrations
# All targets run from the repo root so alembic and `make dev-api` share the
# same cwd (and therefore the same .env, SM_DATABASE_URL, and SQLite path).
migrate:                    ## Run migrations to head
	uv run --project host alembic -c host/alembic.ini upgrade heads

migration:                  ## Create new migration (usage: make migration msg="add foo")
	uv run --project host alembic -c host/alembic.ini revision --autogenerate -m "$(msg)"

downgrade:                  ## Downgrade one revision
	uv run --project host alembic -c host/alembic.ini downgrade -1

# Portability gate for GH #342: revisions are autogenerated on SQLite, which hides
# Boolean-default, expression-index and enum-downgrade defects until Postgres runs
# them. Runs on SM_MIGRATIONS_PG_URL, a DISPOSABLE, already-created database
# (`createdb sm_migrations_check` on the shared dev Postgres); it ends empty.
SM_MIGRATIONS_PG_URL ?= postgresql+asyncpg://postgres:postgres@localhost:5432/sm_migrations_check
ALEMBIC_PG = SM_DATABASE_URL=$(SM_MIGRATIONS_PG_URL) uv run --project host alembic -c host/alembic.ini
migrations-roundtrip-pg:    ## upgrade heads -> downgrade base -> upgrade heads -> alembic check, on Postgres
	$(ALEMBIC_PG) upgrade heads
	$(ALEMBIC_PG) downgrade base
	$(ALEMBIC_PG) upgrade heads
	$(ALEMBIC_PG) check

migration-history:          ## Show migration history
	uv run --project host alembic -c host/alembic.ini history --verbose

# Scaffolding
new-module:                 ## Scaffold a new module (usage: make new-module name=orders)
	@test -n "$(name)" || (echo "Error: Please provide a module name, e.g. make new-module name=orders" && exit 1)
	uv run python scripts/new_module.py $(name)
	uv sync --all-packages
	npm install
	$(MAKE) gen-i18n

# Kill dev servers
kill:
	@echo "Stopping dev servers..."
	@-pkill -f "uvicorn host.main" 2>/dev/null
	@-pkill -f "vite" 2>/dev/null
	@-lsof -ti:8000,5050,5173 | xargs kill -9 2>/dev/null
	@echo "Ports 8000, 5050, 5173 freed."

# Docker — the default app image (./Dockerfile). Standalone: SQLite inside the
# container, no Postgres or Redis needed. Both run targets honour SM_APP_PORT
# so they don't collide with a `make dev` already holding 8000.
SM_APP_PORT ?= 8000
export SM_APP_PORT

docker-build:               ## Build the default app image
	docker build -t simple-module-python .

docker-app: docker-build    ## Run the built image standalone on http://localhost:$(SM_APP_PORT)
	docker run --rm -p $(SM_APP_PORT):8000 \
		-v simple-module-python-data:/app/data \
		simple-module-python

docker-compose-app:         ## Same image via compose (named volume, .env-overridable)
	docker compose up --build app

# Docker — Postgres/Redis now live in the shared ../dev-services stack.
# docker-up brings that shared stack up (idempotent, shared with other repos).
docker-up:
	docker compose -f ../dev-services/compose.yml up -d

# Only stop THIS project's own containers (worker/beat). Never tear down the
# shared stack here — other repos depend on it. Use `make down` in
# ../dev-services to stop the shared services.
docker-down:
	docker compose down

# Celery — local dev (fast reload, no container rebuild)
worker:                     ## Run a Celery worker locally; SM_BG_TASKS_WORKER_QUEUES=a,b limits it to those queues (-Q) and their modules
	@# Normalise like the env parser (strip blanks, drop empty entries): Celery's -Q keeps "gpu, default" as a queue named " default".
	@q=$$(printf '%s' '$(SM_BG_TASKS_WORKER_QUEUES)' | tr -d ' \t' | tr -s ',' | sed 's/^,//;s/,$$//'); \
	set -x; uv run celery -A scripts.run_worker:celery worker -l info $${q:+-Q "$$q"}

beat:                       ## Run the Celery beat scheduler locally
	uv run celery -A scripts.run_worker:celery beat -l info

# Celery — containerized (matches prod image)
worker-docker:              ## Build + run the worker + beat services in docker
	docker compose up --build worker beat

.PHONY: release-check
release-check:
	@test -n "$(version)" || { echo "usage: make release-check version=X.Y.Z"; exit 1; }
	uv run python scripts/bump_version.py $(version) --check
