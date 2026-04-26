.PHONY: install dev dev-api dev-ui build migrate gen-pages

install:
	uv sync
	cd client_app && npm install

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

gen-pages:
	uv run sm gen-pages --host-dir=client_app
