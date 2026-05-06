.PHONY: install dev dev-api dev-ui build migrate migration gen-pages sync-module-deps kill

install:
	uv sync --all-packages
	npm install
	$(MAKE) sync-module-deps

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	cd host && uv run uvicorn main:app --reload --port 8000

dev-ui:
	npm run dev

build:
	npm run build

# Regenerate host/client_app/modules.{manifest.json,generated.ts,generated.css}
# from installed modules (workspace + wheel-installed).
gen-pages:
	cd host && uv run python -m simple_module_hosting gen-pages --host-dir=client_app

# Pull JS deps shipped by wheel-installed modules into host/client_app/node_modules.
# Workspace modules under modules/* don't need this — npm hoists them automatically.
sync-module-deps:
	cd host && uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app

migrate:
	cd host && uv run alembic upgrade head

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	cd host && uv run alembic revision --autogenerate -m "$(msg)"

kill:
	@-pkill -f "uvicorn main:app" 2>/dev/null
	@-pkill -f vite 2>/dev/null
	@-lsof -ti:8000,5050 | xargs kill -9 2>/dev/null
	@echo "Ports 8000, 5050 freed."
