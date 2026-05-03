.PHONY: install dev dev-api dev-ui build migrate migration gen-pages sync-module-deps kill

install:
	uv sync --all-packages
	npm install
	$(MAKE) sync-module-deps

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	$(MAKE) -C host dev-api

dev-ui:
	npm run dev

build:
	npm run build

# Regenerate host/client_app/modules.{manifest.json,generated.ts,generated.css}
# from installed modules (workspace + wheel-installed). Delegates to the
# host's Makefile so the workspace and flat layouts share one command.
gen-pages:
	$(MAKE) -C host gen-pages

# Pull JS deps shipped by wheel-installed modules into host/client_app/node_modules.
# Workspace modules under modules/* don't need this — npm hoists them automatically.
sync-module-deps:
	$(MAKE) -C host sync-js-deps

migrate:
	$(MAKE) -C host migrate

migration:
	$(MAKE) -C host migration msg="$(msg)"

kill:
	@-pkill -f "uvicorn main:app" 2>/dev/null
	@-pkill -f vite 2>/dev/null
	@-lsof -ti:8000,5050 | xargs kill -9 2>/dev/null
	@echo "Ports 8000, 5050 freed."
