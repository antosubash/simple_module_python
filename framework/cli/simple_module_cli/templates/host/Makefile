.PHONY: install dev dev-api dev-ui build migrate migration gen-pages sync-js-deps

install:
	uv sync
	cd client_app && npm install
	$(MAKE) sync-js-deps

dev: gen-pages
	@echo "Starting API and UI dev servers..."
	$(MAKE) -j2 dev-api dev-ui

dev-api:
	uv run uvicorn main:app --reload --port 8000

dev-ui:
	cd client_app && npm run dev

build:
	cd client_app && npm run build

migrate:
	uv run alembic upgrade head

migration:
	@test -n "$(msg)" || (echo 'Usage: make migration msg="describe the change"' && exit 1)
	uv run alembic revision --autogenerate -m "$(msg)"

gen-pages:
	uv run python -m simple_module_hosting gen-pages --host-dir=client_app

sync-js-deps:
	uv run python -m simple_module_hosting sync-js-deps --host-client-app=client_app
